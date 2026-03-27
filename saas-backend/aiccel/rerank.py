import os
from typing import Any


try:
    if os.environ.get("AICCEL_LIGHTWEIGHT", "false").lower() == "true":
        FLAG_EMBEDDING_AVAILABLE = False
    else:
        from FlagEmbedding import FlagModel
        FLAG_EMBEDDING_AVAILABLE = True
except ImportError:
    FLAG_EMBEDDING_AVAILABLE = False
except Exception:
    FLAG_EMBEDDING_AVAILABLE = False

class NeuralReranker:
    """
    AICCEL Neural Reranker using BAAI/bge-base-en-v1.5.

    This uses the `FlagEmbedding` library, which is the official optimized runtime
    for BAAI's BGE (Beijing General Embedding) models. It ensures standardized
    pre-processing, instruction formatting, and efficient pooling for retrieval tasks,
    providing better accuracy than generic transformer implementations for this specific model family.
    """
    def __init__(self, model_name: str = 'BAAI/bge-base-en-v1.5', use_fp16: bool = False):
        self.model_name = model_name
        self.use_fp16 = use_fp16
        self._model = None
        self.available = FLAG_EMBEDDING_AVAILABLE

    def _load_model(self):
        """Lazy loads the BGE model."""
        if not self.available:
            raise ImportError(
                "FlagEmbedding package is not installed. Neural Reranking disabled. "
                "Install with `pip install FlagEmbedding`. "
                "Run 'aiccel check' to verify environment."
            )

        if self._model is None:
            print(f"Loading Neural Reranker Model: {self.model_name}...")
            # Initialize BGE Model
            self._model = FlagModel(
                self.model_name,
                query_instruction_for_retrieval="Represent this sentence for searching relevant passages: ",
                use_fp16=self.use_fp16
            )
            print("Neural Reranker Model loaded successfully.")

    def rank(self, query: str, documents: list[str]) -> list[dict[str, Any]]:
        """
        Rerank a list of documents based on semantic similarity to the query.
        """
        if not documents:
            return []

        if not self.available:
             raise RuntimeError("Neural Reranking is unavailable. FlagEmbedding library not found.")

        try:
            self._load_model()

            # Encode
            q_embeddings = self._model.encode_queries([query])
            p_embeddings = self._model.encode(documents)

            # Calculate scores (dot product)
            scores = q_embeddings @ p_embeddings.T

            # Handle shape (1, N) -> (N,)
            if len(scores.shape) > 1:
                scores = scores[0]

            results = []
            for i, doc in enumerate(documents):
                results.append({
                    "text": doc,
                    "score": float(scores[i]),
                    "original_index": i
                })

            # Sort by score descending
            results.sort(key=lambda x: x['score'], reverse=True)
            return results

        except Exception as e:
            print(f"Reranking validation error: {e}")
            raise e
