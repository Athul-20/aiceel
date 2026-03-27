# aiccel/providers/groq.py
"""
Groq Provider Implementation
============================
"""

from typing import Optional, Union

import orjson
from aiohttp import ClientSession, ClientTimeout

from .base import LLMProvider


class GroqProvider(LLMProvider):
    """
    Groq LLM Provider for ultra-fast inference.

    Groq provides extremely fast inference for open-source models like
    LLaMA, Mixtral, and Gemma.
    """

    ENV_KEY_PREFIX = "GROQ"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama3-70b-8192",
        embedding_provider: Optional[LLMProvider] = None,
        verbose: bool = False,
        log_file: Optional[str] = None,
        structured_logging: bool = False
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            verbose=verbose,
            log_file=log_file,
            structured_logging=structured_logging
        )
        self.embedding_provider = embedding_provider
        self.http_session = None

    async def __aenter__(self):
        self.http_session = ClientSession(timeout=ClientTimeout(total=30))
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.http_session:
            await self.http_session.close()

    def _generate_impl(self, prompt: str, **kwargs) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    async def _generate_async_impl(self, prompt: str, **kwargs) -> str:
        return await self.chat_async([{"role": "user", "content": prompt}], **kwargs)

    def _chat_impl(self, messages: list[dict[str, str]], **kwargs) -> str:
        trace_id = self.logger.trace_start("groq_chat", {"message_count": len(messages)})
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens)
        }

        try:
            session = self._get_sync_session()
            response = session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            response_json = orjson.loads(response.content)

            result = response_json["choices"][0]["message"]["content"]
            self.logger.trace_end(trace_id, {"response": result[:100]})
            return result
        except Exception as e:
            self.logger.trace_error(trace_id, e, "Groq chat failed")
            raise

    async def _chat_async_impl(self, messages: list[dict[str, str]], **kwargs) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens)
        }

        session = self.http_session or ClientSession(timeout=ClientTimeout(total=self.timeout))
        close_session = self.http_session is None

        try:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data
            ) as response:
                response.raise_for_status()
                response_json = await response.json()
                result = response_json["choices"][0]["message"]["content"]
                return result
        finally:
            if close_session:
                await session.close()

    def _embed_impl(self, text: Union[str, list[str]]) -> list[float]:
        if not self.embedding_provider:
            raise ValueError("No embedding provider specified")
        return self.embedding_provider.embed(text)

    async def _embed_async_impl(self, text: Union[str, list[str]]) -> list[float]:
        if not self.embedding_provider:
            raise ValueError("No embedding provider specified")
        return await self.embedding_provider.embed_async(text)
