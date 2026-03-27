from abc import ABC, abstractmethod
from typing import Union

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    def embed(self, texts: Union[str, list[str]]) -> list[list[float]]:
        """
        Generate embeddings for one or more texts.

        Args:
            texts: A single string or list of strings to embed.

        Returns:
            A list of embeddings, where each embedding is a list of floats.
        """
        raise NotImplementedError

    @abstractmethod
    def get_dimension(self) -> int:
        """
        Return the dimension of the embeddings produced by this provider.

        Returns:
            The embedding dimension (e.g., 1536 for OpenAI text-embedding-3-small).
        """
        raise NotImplementedError


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider for OpenAI's embedding models."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        """
        Initialize the OpenAI embedding provider.

        Args:
            api_key: OpenAI API key.
            model: Embedding model name (e.g., 'text-embedding-3-small').
        """
        if openai is None:
            raise ImportError("openai package is required. Install with: pip install openai>=1.0.0")

        self.client = openai.Client(api_key=api_key)
        self.model = model
        self._dimension = None  # Set after first embedding call

    def embed(self, texts: Union[str, list[str]]) -> list[list[float]]:
        """
        Generate embeddings using OpenAI's embedding model.

        Args:
            texts: A single string or list of strings to embed.

        Returns:
            A list of embeddings.
        """
        if isinstance(texts, str):
            texts = [texts]

        try:
            response = self.client.embeddings.create(
                input=texts,
                model=self.model,
            )
            embeddings = [data.embedding for data in response.data]

            # Set dimension on first call
            if self._dimension is None and embeddings:
                self._dimension = len(embeddings[0])

            return embeddings
        except Exception as e:  # pragma: no cover
            raise Exception(f"OpenAI embedding error: {e!s}")

    def get_dimension(self) -> int:
        """
        Return the embedding dimension.

        Returns:
            The dimension of the embeddings (e.g., 1536 for text-embedding-3-small).

        Raises:
            ValueError: If dimension is not yet known.
        """
        if self._dimension is None:
            # Generate a dummy embedding to get dimension
            dummy_embedding = self.embed("test")[0]
            self._dimension = len(dummy_embedding)
        return self._dimension


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Embedding provider for Google's Gemini embedding models."""

    def __init__(self, api_key: str, model: str = "embedding-001"):
        """
        Initialize the Gemini embedding provider.

        Args:
            api_key: Google API key.
            model: Embedding model name (e.g., 'embedding-001').
        """
        if genai is None:
            raise ImportError(
                "google-generativeai package is required. Install with: pip install google-generativeai>=0.3.0"
            )

        genai.configure(api_key=api_key)
        self.model = f"models/{model}"
        self._dimension = 768  # Known dimension for embedding-001

    def embed(self, texts: Union[str, list[str]]) -> list[list[float]]:
        """
        Generate embeddings using Gemini's embedding model.

        Args:
            texts: A single string or list of strings to embed.

        Returns:
            A list of embeddings.
        """
        if isinstance(texts, str):
            texts = [texts]

        try:
            response = genai.embed_content(
                model=self.model,
                content=texts,
                task_type="retrieval_document",
            )
            return response["embedding"]
        except Exception as e:  # pragma: no cover
            raise Exception(f"Gemini embedding error: {e!s}")

    def get_dimension(self) -> int:
        """Return the embedding dimension."""
        return self._dimension
