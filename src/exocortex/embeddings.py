"""Embedding engine for Exocortex using fastembed."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from .config import get_config

if TYPE_CHECKING:
    from fastembed import TextEmbedding

logger = logging.getLogger(__name__)


class EmbeddingEngine:
    """Handles text embedding using fastembed.

    Uses lazy loading to avoid slow startup times.
    """

    def __init__(self, model_name: str | None = None) -> None:
        """Initialize the embedding engine.

        Args:
            model_name: Name of the embedding model. If None, uses config default.
        """
        self._model: "TextEmbedding | None" = None
        self._model_name = model_name or get_config().embedding_model
        self._dimension: int | None = None

    @property
    def model(self) -> "TextEmbedding":
        """Get the embedding model, loading it lazily if needed."""
        if self._model is None:
            logger.info(f"Loading embedding model: {self._model_name}")
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
            logger.info("Embedding model loaded successfully")
        return self._model

    @property
    def dimension(self) -> int:
        """Get the embedding dimension for the current model."""
        if self._dimension is None:
            # Get dimension by embedding a test string
            test_embedding = list(self.model.embed(["test"]))[0]
            self._dimension = len(test_embedding)
            logger.debug(f"Embedding dimension: {self._dimension}")
        return self._dimension

    def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Args:
            text: Text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        embeddings = list(self.model.embed([text]))
        return embeddings[0].tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        embeddings = list(self.model.embed(texts))
        return [emb.tolist() for emb in embeddings]

    def compute_similarity(
        self, embedding1: list[float], embedding2: list[float]
    ) -> float:
        """Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector.
            embedding2: Second embedding vector.

        Returns:
            Cosine similarity score (0 to 1).
        """
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)

        # Cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))


# Global embedding engine instance (lazy loaded)
_embedding_engine: EmbeddingEngine | None = None


def get_embedding_engine() -> EmbeddingEngine:
    """Get the global embedding engine instance."""
    global _embedding_engine
    if _embedding_engine is None:
        _embedding_engine = EmbeddingEngine()
    return _embedding_engine


def reset_embedding_engine() -> None:
    """Reset the global embedding engine (useful for testing)."""
    global _embedding_engine
    _embedding_engine = None

