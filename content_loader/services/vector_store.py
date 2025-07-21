"""Vector database service for storing and retrieving embeddings."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from content_loader.core.models import ProcessedChunk

logger = logging.getLogger(__name__)


class VectorStore:
    """Service for storing and retrieving document embeddings."""

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        collection_name: str = "documents",
    ):
        """Initialize vector store.

        Args:
            qdrant_url: URL of Qdrant server
            collection_name: Name of the collection to store vectors
        """
        self.qdrant_url = qdrant_url
        self.collection_name = collection_name
        self._client: Optional[AsyncQdrantClient] = None
        logger.info(f"Initializing vector store: {qdrant_url}/{collection_name}")

    def _get_client(self) -> AsyncQdrantClient:
        """Get or create Qdrant client."""
        if self._client is None:
            self._client = AsyncQdrantClient(url=self.qdrant_url)
        return self._client

    async def ensure_collection(self, vector_dimension: int) -> None:
        """Ensure collection exists with proper configuration.

        Args:
            vector_dimension: Dimension of the vectors to store
        """
        client = self._get_client()

        try:
            collections = await client.get_collections()
            collection_exists = any(
                col.name == self.collection_name for col in collections.collections
            )

            if not collection_exists:
                logger.info(f"Creating collection: {self.collection_name}")
                await client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=vector_dimension, distance=Distance.COSINE
                    ),
                )
                logger.info(f"Collection {self.collection_name} created successfully")
            else:
                logger.info(f"Collection {self.collection_name} already exists")

        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")
            raise

    async def store_embeddings(
        self, chunks: List[ProcessedChunk], embeddings: List[List[float]]
    ) -> None:
        """Store document chunks with their embeddings.

        Args:
            chunks: List of processed document chunks
            embeddings: Corresponding embedding vectors
        """
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks must match number of embeddings")

        client = self._get_client()
        points = []

        for chunk, embedding in zip(chunks, embeddings):
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload=chunk.to_vector_payload(),
            )
            points.append(point)

        try:
            await client.upsert(collection_name=self.collection_name, points=points)
            logger.info(f"Stored {len(points)} embeddings in vector database")

        except Exception as e:
            logger.error(f"Error storing embeddings: {e}")
            raise

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 10,
        score_threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Search for similar documents.

        Args:
            query_embedding: Query vector
            limit: Maximum number of results to return
            score_threshold: Minimum similarity score

        Returns:
            List of search results with metadata
        """
        client = self._get_client()

        try:
            results = await client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )

            return [
                {"id": result.id, "score": result.score, "payload": result.payload}
                for result in results
            ]

        except Exception as e:
            logger.error(f"Error searching vectors: {e}")
            raise

    async def get_collection_info(self) -> Dict[str, Any]:
        """Get collection information.

        Returns:
            Collection statistics and information
        """
        client = self._get_client()

        try:
            info = await client.get_collection(self.collection_name)
            return {
                "status": info.status,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "config": {
                    "distance": (
                        getattr(
                            info.config.params.vectors, "distance", Distance.COSINE
                        ).value
                        if info.config.params.vectors
                        else "cosine"
                    ),
                    "size": (
                        getattr(info.config.params.vectors, "size", 384)
                        if info.config.params.vectors
                        else 384
                    ),
                },
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            raise

    async def close(self) -> None:
        """Close the client connection."""
        if self._client:
            await self._client.close()
            self._client = None
