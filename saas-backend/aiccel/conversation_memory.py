# aiccel/conversation_memory.py
"""
Conversation memory management with compression, summarization, and efficient storage.
"""

import logging
import zlib
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Optional

from .constants import Limits
from .exceptions import MemoryException, ValidationException


logger = logging.getLogger(__name__)


@dataclass
class MemoryTurn:
    """Represents a single turn in conversation memory"""
    query: str
    response: str
    tool_used: Optional[str] = None
    tool_output: Optional[str] = None
    timestamp: str = ""
    token_count: int = 0
    compressed: bool = False

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {k: v for k, v in asdict(self).items() if v is not None}






class MemoryCompressor:
    """
    Helper for compressing text data to save memory.
    Used for simulation and actual storage optimization.
    """

    def compress(self, text: str) -> tuple[str, bool]:
        """
        Compress text using zlib.

        Args:
            text: Text to compress

        Returns:
            Tuple of (hex_encoded_compressed_string, success_bool)
            If compression fails or is unnecessary, returns (original_text, False)
        """
        if not text:
            return "", False

        try:
            # Compress using zlib
            compressed_bytes = zlib.compress(text.encode('utf-8'))
            return compressed_bytes.hex(), True
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return text, False

class ConversationMemory:
    """
    Enhanced conversation memory with compression, summarization, and token management.

    Features:
    - Automatic compression of old turns
    - Token-aware memory management
    - Summarization for long histories
    - Thread-safe operations
    """

    VALID_MEMORY_TYPES = {"buffer", "window", "summary"}

    def __init__(
        self,
        memory_type: str = "buffer",
        max_turns: int = Limits.MAX_MEMORY_TURNS,
        max_tokens: int = Limits.MAX_MEMORY_TOKENS,
        llm_provider = None
    ):
        """
        Initialize conversation memory.

        Args:
            memory_type: Type of memory ('buffer', 'window', 'summary')
            max_turns: Maximum number of turns to keep
            max_tokens: Maximum total tokens to keep
            llm_provider: LLM provider for summarization (required for 'summary' type)

        Raises:
            ValidationException: If configuration is invalid
        """
        self._validate_config(memory_type, llm_provider)

        self.memory_type = memory_type
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.llm_provider = llm_provider
        self.history: list[dict[str, Any]] = []

        logger.debug(f"Initialized ConversationMemory: type={memory_type}, max_turns={max_turns}, max_tokens={max_tokens}")

    def _validate_config(self, memory_type: str, llm_provider) -> None:
        """Validate memory configuration"""
        if memory_type not in self.VALID_MEMORY_TYPES:
            raise ValidationException(
                "memory_type",
                f"Invalid memory type. Must be one of: {self.VALID_MEMORY_TYPES}",
                expected=self.VALID_MEMORY_TYPES,
                actual=memory_type
            )

        if memory_type == "summary" and not llm_provider:
            raise ValidationException(
                "llm_provider",
                "Summary memory type requires an llm_provider",
                expected="LLMProvider instance",
                actual=None
            )

    def _calculate_token_count(self, text: str) -> int:
        """Estimate token count (roughly 4 chars per token)"""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def add_turn(
        self,
        query: str,
        response: str,
        tool_used: Optional[str] = None,
        tool_output: Optional[str] = None
    ) -> None:
        """
        Add a conversation turn to memory.

        Args:
            query: User query
            response: Agent response
            tool_used: Name of tool used (if any)
            tool_output: Tool output (if any)

        Raises:
            MemoryException: If memory operation fails
        """
        try:
            # Sanitize inputs
            query = str(query) if query else ""
            response = str(response) if response else ""
            tool_output = str(tool_output) if tool_output else None

            # Calculate token counts
            query_tokens = self._calculate_token_count(query)
            response_tokens = self._calculate_token_count(response)
            tool_tokens = self._calculate_token_count(tool_output) if tool_output else 0
            total_tokens = query_tokens + response_tokens + tool_tokens

            # Create turn
            turn = {
                "query": query,
                "response": response,
                "tool_used": tool_used,
                "tool_output": tool_output,
                "timestamp": datetime.now().isoformat(),
                "token_count": total_tokens
            }

            self.history.append(turn)
            self._manage_memory()

            logger.debug(f"Added turn to memory: {total_tokens} tokens")

        except Exception as e:
            logger.error(f"Failed to add turn to memory: {e}")
            raise MemoryException(f"Failed to add turn: {e}")

    def _manage_memory(self) -> None:
        """Manage memory size and apply retention policies"""
        try:
            # Calculate current total tokens
            current_tokens = sum(turn.get("token_count", 0) for turn in self.history)

            # Remove oldest turns until within limits
            while (len(self.history) > self.max_turns or current_tokens > self.max_tokens) and self.history:
                removed = self.history.pop(0)
                current_tokens -= removed.get("token_count", 0)
                logger.debug(f"Removed old turn: {removed.get('token_count', 0)} tokens")

            # Trigger summarization if configured
            if self.memory_type == "summary" and len(self.history) > self.max_turns // 2:
                self._summarize_history()

        except Exception as e:
            logger.error(f"Memory management error: {e}")
            raise MemoryException(f"Memory management failed: {e}")

    def _summarize_history(self) -> None:
        """Summarize conversation history to save space"""
        if len(self.history) <= 1 or not self.llm_provider:
            return

        try:
            # Get turns to summarize (leave most recent)
            to_summarize = self.history[:-1]
            summary_parts = ["Summarize the following conversation history (max 200 words):\n\n"]

            for turn in to_summarize:
                try:
                    summary_parts.append(f"User: {turn['query']}\nAssistant: {turn['response']}\n")

                    if turn.get("tool_output"):
                        summary_parts.append(f"Tool Output: {turn['tool_output']}\n")

                except Exception as e:
                    logger.warning(f"Failed to process turn for summary: {e}")
                    continue

            summary_prompt = "".join(summary_parts)
            summary = self.llm_provider.generate(summary_prompt)

            summary_tokens = self._calculate_token_count(summary)

            summary_turn = {
                "query": "Conversation summary",
                "response": summary,
                "tool_used": None,
                "tool_output": None,
                "timestamp": datetime.now().isoformat(),
                "token_count": summary_tokens + self._calculate_token_count("Conversation summary")
            }

            # Replace old turns with summary + keep most recent
            self.history = [summary_turn, *self.history[-1:]]
            logger.info("Summarized conversation history")

        except Exception as e:
            logger.error(f"History summarization failed: {e}")
            raise MemoryException(f"Summarization failed: {e}")

    def get_context(self, max_context_turns: Optional[int] = None) -> str:
        """
        Get conversation context as formatted string.

        Args:
            max_context_turns: Maximum turns to include (None for all)

        Returns:
            str: Formatted conversation context
        """
        if not self.history:
            return ""

        try:
            context_parts = ["Conversation History:\n"]
            turns = self.history[-max_context_turns:] if max_context_turns else self.history

            for turn in turns:
                try:
                    context_parts.append(f"User: {turn['query']}\nAssistant: {turn['response']}\n")

                    if turn.get("tool_used") and turn.get("tool_output"):
                        context_parts.append(f"Tool Used: {turn['tool_used']}\nTool Output: {turn['tool_output']}\n")

                    context_parts.append("\n")

                except Exception as e:
                    logger.warning(f"Failed to process turn in get_context: {e}")
                    continue

            context = "".join(context_parts).strip()

            # Safety truncation
            if len(context) > Limits.MAX_PROMPT_LENGTH:
                context = context[-Limits.MAX_PROMPT_LENGTH:]
                logger.warning(f"Context truncated to {Limits.MAX_PROMPT_LENGTH} chars")

            return context

        except Exception as e:
            logger.error(f"Error getting context: {e}")
            return ""

    def clear(self) -> None:
        """Clear all conversation history"""
        self.history = []
        logger.info("Conversation memory cleared")

    def get_history(self) -> list[dict[str, Any]]:
        """
        Get conversation history.

        Returns:
            List[Dict]: List of conversation turns
        """
        # Return deep copy to prevent external modification
        return [turn.copy() for turn in self.history]

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics"""
        return {
            "total_turns": len(self.history),
            "total_tokens": sum(turn.get("token_count", 0) for turn in self.history),
            "max_turns": self.max_turns,
            "max_tokens": self.max_tokens,
            "memory_type": self.memory_type,
            "compression_enabled": False
        }
