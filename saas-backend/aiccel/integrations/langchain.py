# aiccel/integrations/langchain.py
"""
LangChain Integration
======================

Adapters for using AICCEL with LangChain.
"""

from typing import TYPE_CHECKING, Optional


if TYPE_CHECKING:
    from ..agent_slim import SlimAgent


class LangChainAdapter:
    """
    Adapt AICCEL agents for use with LangChain.

    Usage:
        from aiccel import SlimAgent
        from aiccel.integrations import LangChainAdapter

        agent = SlimAgent(provider=...)
        lc_tool = LangChainAdapter.as_tool(agent)

        # Use in LangChain
        chain = lc_tool | other_chain
    """

    @staticmethod
    def as_tool(agent: 'SlimAgent', name: Optional[str] = None, description: Optional[str] = None):
        """
        Convert AICCEL agent to LangChain Tool.

        Requires: langchain installed
        """
        try:
            from langchain.tools import Tool
        except ImportError:
            raise ImportError("langchain required: pip install langchain")

        def run_agent(query: str) -> str:
            result = agent.run(query)
            return result.get("response", "")

        async def arun_agent(query: str) -> str:
            result = await agent.run_async(query)
            return result.get("response", "")

        return Tool(
            name=name or agent.config.name,
            description=description or agent.config.description,
            func=run_agent,
            coroutine=arun_agent
        )

    @staticmethod
    def as_runnable(agent: 'SlimAgent'):
        """
        Convert AICCEL agent to LangChain Runnable.

        Requires: langchain installed
        """
        try:
            from langchain_core.runnables import RunnableLambda
        except ImportError:
            raise ImportError("langchain-core required: pip install langchain-core")

        async def invoke(input_data):
            if isinstance(input_data, str):
                query = input_data
            elif isinstance(input_data, dict):
                query = input_data.get("query") or input_data.get("input", "")
            else:
                query = str(input_data)

            result = await agent.run_async(query)
            return result

        return RunnableLambda(invoke)

    @staticmethod
    def from_langchain_llm(llm):
        """
        Create AICCEL provider from LangChain LLM.

        Usage:
            from langchain_openai import ChatOpenAI
            lc_llm = ChatOpenAI(model="gpt-4")
            provider = LangChainAdapter.from_langchain_llm(lc_llm)
        """
        from ..providers import LLMProvider

        class LangChainProvider(LLMProvider):
            def __init__(self, lc_llm):
                self.llm = lc_llm
                super().__init__(api_key="langchain", model="langchain")

            def generate(self, prompt: str, **kwargs) -> str:
                if hasattr(self.llm, 'invoke'):
                    return self.llm.invoke(prompt).content
                return self.llm(prompt)

            async def generate_async(self, prompt: str, **kwargs) -> str:
                if hasattr(self.llm, 'ainvoke'):
                    result = await self.llm.ainvoke(prompt)
                    return result.content
                return self.generate(prompt)

        return LangChainProvider(llm)
