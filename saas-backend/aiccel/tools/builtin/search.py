# aiccel/tools_v2/builtin/search.py
"""
Search Tool - No Hardcoded APIs
================================

Provides web search functionality via pluggable providers.
All endpoints and API configurations are fully customizable.

Usage:
    # Auto-configure from environment
    search = SearchTool()  # Uses SEARCH_PROVIDER, SEARCH_API_KEY, SEARCH_ENDPOINT

    # Or configure explicitly
    search = SearchTool(
        provider="serper",
        api_key="your-key",
        endpoint="https://google.serper.dev/search"  # Optional custom endpoint
    )

    # Use custom provider
    class MySearchProvider(SearchProvider):
        def search(self, query, **options):
            # Custom implementation
            pass

    search = SearchTool(provider=MySearchProvider(api_key="..."))
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Union

import requests

from ..base import (
    BaseTool,
    ParameterSchema,
    ParameterType,
    ToolConfigurationError,
    ToolExecutionError,
    ToolResult,
)


logger = logging.getLogger(__name__)


# =============================================================================
# SEARCH RESULT DATA STRUCTURE
# =============================================================================

@dataclass
class SearchResult:
    """A single search result"""
    title: str
    url: str
    snippet: str
    position: int = 0

    def __str__(self) -> str:
        return f"{self.title}\nURL: {self.url}\n{self.snippet}"


@dataclass
class SearchResponse:
    """Complete search response"""
    query: str
    results: list[SearchResult]
    knowledge_graph: Optional[dict[str, Any]] = None
    total_results: Optional[int] = None

    def to_text(self) -> str:
        """Format as readable text"""
        parts = [f"Search results for '{self.query}':\n"]

        for i, result in enumerate(self.results, 1):
            parts.append(f"{i}. {result.title}")
            parts.append(f"   URL: {result.url}")
            parts.append(f"   {result.snippet}\n")

        if self.knowledge_graph:
            kg_title = self.knowledge_graph.get("title", "")
            kg_desc = self.knowledge_graph.get("description", "")
            if kg_title and kg_desc:
                parts.append(f"\nKnowledge Graph: {kg_title} - {kg_desc}")

        return "\n".join(parts)


# =============================================================================
# SEARCH PROVIDER INTERFACE
# =============================================================================

class SearchProvider(ABC):
    """
    Abstract interface for search providers.

    Implement this to add a new search backend.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name"""
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        num_results: int = 10,
        **options
    ) -> SearchResponse:
        """
        Perform a search.

        Args:
            query: Search query
            num_results: Number of results to return
            **options: Provider-specific options

        Returns:
            SearchResponse with results
        """
        pass


# =============================================================================
# SERPER PROVIDER (google.serper.dev)
# =============================================================================

class SerperSearchProvider(SearchProvider):
    """Search provider using Serper API"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: float = 15.0
    ):
        self.api_key = api_key or os.getenv("SERPER_API_KEY") or os.getenv("SEARCH_API_KEY")
        self.endpoint = endpoint or os.getenv("SERPER_ENDPOINT") or "https://google.serper.dev/search"
        self.timeout = timeout
        self._session = requests.Session()

        if not self.api_key:
            logger.warning("SerperSearchProvider: No API key provided")

    @property
    def name(self) -> str:
        return "serper"

    def search(
        self,
        query: str,
        num_results: int = 10,
        **options
    ) -> SearchResponse:
        """Perform search via Serper API"""
        if not self.api_key:
            raise ToolConfigurationError("Serper API key not configured")

        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }

        payload = {
            "q": query,
            "num": num_results,
            **options
        }

        try:
            response = self._session.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_response(query, data)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise ToolConfigurationError("Invalid Serper API key")
            elif e.response.status_code == 429:
                raise ToolExecutionError("Rate limit exceeded")
            raise ToolExecutionError(f"Serper API error: {e}")
        except requests.exceptions.RequestException as e:
            raise ToolExecutionError(f"Network error: {e}")

    def _parse_response(self, query: str, data: dict[str, Any]) -> SearchResponse:
        """Parse Serper API response"""
        results = []

        for i, item in enumerate(data.get("organic", []), 1):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                position=i
            ))

        kg = data.get("knowledgeGraph")

        return SearchResponse(
            query=query,
            results=results,
            knowledge_graph=kg
        )


# =============================================================================
# TAVILY PROVIDER (tavily.com)
# =============================================================================

class TavilySearchProvider(SearchProvider):
    """Search provider using Tavily API"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: float = 15.0
    ):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.endpoint = endpoint or os.getenv("TAVILY_ENDPOINT") or "https://api.tavily.com/search"
        self.timeout = timeout
        self._session = requests.Session()

        if not self.api_key:
            logger.warning("TavilySearchProvider: No API key provided")

    @property
    def name(self) -> str:
        return "tavily"

    def search(
        self,
        query: str,
        num_results: int = 10,
        **options
    ) -> SearchResponse:
        """Perform search via Tavily API"""
        if not self.api_key:
            raise ToolConfigurationError("Tavily API key not configured")

        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": num_results,
            **options
        }

        try:
            response = self._session.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_response(query, data)

        except requests.exceptions.HTTPError as e:
            raise ToolExecutionError(f"Tavily API error: {e}")
        except requests.exceptions.RequestException as e:
            raise ToolExecutionError(f"Network error: {e}")

    def _parse_response(self, query: str, data: dict[str, Any]) -> SearchResponse:
        """Parse Tavily API response"""
        results = []

        for i, item in enumerate(data.get("results", []), 1):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                position=i
            ))

        return SearchResponse(
            query=query,
            results=results
        )


# =============================================================================
# BRAVE SEARCH PROVIDER
# =============================================================================

class BraveSearchProvider(SearchProvider):
    """Search provider using Brave Search API"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: float = 15.0
    ):
        self.api_key = api_key or os.getenv("BRAVE_API_KEY")
        self.endpoint = endpoint or os.getenv("BRAVE_ENDPOINT") or "https://api.search.brave.com/res/v1/web/search"
        self.timeout = timeout
        self._session = requests.Session()

    @property
    def name(self) -> str:
        return "brave"

    def search(
        self,
        query: str,
        num_results: int = 10,
        **options
    ) -> SearchResponse:
        """Perform search via Brave API"""
        if not self.api_key:
            raise ToolConfigurationError("Brave API key not configured")

        headers = {
            "X-Subscription-Token": self.api_key,
            "Accept": "application/json"
        }

        params = {
            "q": query,
            "count": num_results,
            **options
        }

        try:
            response = self._session.get(
                self.endpoint,
                headers=headers,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_response(query, data)

        except requests.exceptions.RequestException as e:
            raise ToolExecutionError(f"Brave API error: {e}")

    def _parse_response(self, query: str, data: dict[str, Any]) -> SearchResponse:
        """Parse Brave API response"""
        results = []

        web_results = data.get("web", {}).get("results", [])
        for i, item in enumerate(web_results, 1):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
                position=i
            ))

        return SearchResponse(
            query=query,
            results=results
        )


# =============================================================================
# PROVIDER FACTORY
# =============================================================================

def get_search_provider(
    provider: Optional[Union[str, SearchProvider]] = None,
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None
) -> SearchProvider:
    """
    Get a search provider by name or return the provided instance.

    Args:
        provider: Provider name ("serper", "tavily", "brave") or instance
        api_key: API key for the provider
        endpoint: Custom endpoint URL

    Returns:
        SearchProvider instance
    """
    if isinstance(provider, SearchProvider):
        return provider

    # Get from environment if not specified
    provider_name = provider or os.getenv("SEARCH_PROVIDER", "serper")

    providers = {
        "serper": SerperSearchProvider,
        "tavily": TavilySearchProvider,
        "brave": BraveSearchProvider,
    }

    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        raise ToolConfigurationError(f"Unknown search provider: {provider_name}")

    return provider_class(api_key=api_key, endpoint=endpoint)


# =============================================================================
# SEARCH TOOL
# =============================================================================

class SearchTool(BaseTool):
    """
    Web search tool with pluggable providers.

    No hardcoded API endpoints - all configuration via:
    - Constructor parameters
    - Environment variables (SEARCH_PROVIDER, SEARCH_API_KEY, etc.)
    - Custom provider instances

    Usage:
        # Auto-configure from environment
        search = SearchTool()

        # Explicit configuration
        search = SearchTool(provider="serper", api_key="your-key")

        # Custom provider
        search = SearchTool(provider=MyCustomProvider())
    """

    def __init__(
        self,
        provider: Optional[Union[str, SearchProvider]] = None,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: float = 15.0,
        max_results: int = 5
    ):
        self._provider = get_search_provider(provider, api_key, endpoint)
        self._max_results = max_results

        # Define schema
        parameters = [
            ParameterSchema(
                name="query",
                type=ParameterType.STRING,
                description="The search query",
                required=True,
                min_length=1,
                max_length=500
            ),
            ParameterSchema(
                name="num_results",
                type=ParameterType.INTEGER,
                description="Number of results to return (default: 5)",
                required=False,
                default=5
            )
        ]

        super().__init__(
            name="search",
            description="Search the web for current information on any topic",
            parameters=parameters,
            timeout=timeout
        )

        # Add examples
        self.add_example({"name": "search", "args": {"query": "latest AI news"}})
        self.add_example({"name": "search", "args": {"query": "who is the CEO of OpenAI"}})

    @property
    def provider(self) -> SearchProvider:
        """Get the search provider"""
        return self._provider

    def _execute(self, args: dict[str, Any]) -> Any:
        """Execute the search"""
        query = args.get("query") or args.get("q") or args.get("search")
        if not query:
            return ToolResult.fail("No search query provided")

        num_results = args.get("num_results", self._max_results)

        logger.info(f"Searching with {self._provider.name}: {query}")

        try:
            response = self._provider.search(
                query=query,
                num_results=num_results
            )

            return response.to_text()

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise
