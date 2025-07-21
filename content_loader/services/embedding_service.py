"""Embedding service for converting text to vectors."""

import logging
from typing import List, Optional

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating text embeddings."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize embedding service with specified model.

        Args:
            model_name: Name of the sentence transformer model to use
        """
        self.model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        logger.info(f"Initializing embedding service with model: {model_name}")

    def _load_model(self) -> SentenceTransformer:
        """Lazy load the embedding model."""
        if self._model is None:
            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            logger.info("Embedding model loaded successfully")
        return self._model

    def embed_text(self, text: str) -> List[float]:
        """Convert single text to embedding vector.

        Args:
            text: Text to embed

        Returns:
            List of float values representing the embedding vector
        """
        model = self._load_model()
        embedding = model.encode(text, convert_to_tensor=False)
        return embedding.tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Convert multiple texts to embedding vectors.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        model = self._load_model()
        embeddings = model.encode(texts, convert_to_tensor=False)
        return [embedding.tolist() for embedding in embeddings]

    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by this model.

        Returns:
            Dimension of embedding vectors
        """
        model = self._load_model()
        dimension = model.get_sentence_embedding_dimension()
        return dimension if dimension is not None else 384
