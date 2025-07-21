"""Document processing service for chunking and embedding."""

import logging
from typing import AsyncGenerator, List

from content_loader.core.models import ChunkType, Document, ProcessedChunk

from .embedding_service import EmbeddingService
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Service for processing documents through the embedding pipeline."""

    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore):
        """Initialize document processor.

        Args:
            embedding_service: Service for generating embeddings
            vector_store: Service for storing vectors
        """
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        logger.info("Document processor initialized")

    def chunk_document(
        self, document: Document, chunk_size: int = 500
    ) -> List[ProcessedChunk]:
        """Split document into chunks for processing.

        Args:
            document: Document to chunk
            chunk_size: Maximum characters per chunk

        Returns:
            List of processed chunks
        """
        text = document.text
        if not text:
            return []

        chunks: List[ProcessedChunk] = []

        # Simple text chunking by character count
        for i in range(0, len(text), chunk_size):
            chunk_text = text[i : i + chunk_size]

            # Try to break at word boundaries
            if i + chunk_size < len(text) and not text[i + chunk_size].isspace():
                # Find the last space in the chunk
                last_space = chunk_text.rfind(" ")
                if (
                    last_space > chunk_size * 0.5
                ):  # Only break if we don't lose too much
                    chunk_text = chunk_text[:last_space]

            chunk = ProcessedChunk(
                id=f"{document.id}_chunk_{len(chunks)}",
                text=chunk_text.strip(),
                chunk_type=ChunkType.TEXT,
                chunk_index=len(chunks),
                document_id=document.id,
                source_metadata=document.metadata,
            )
            chunks.append(chunk)

        logger.info(f"Document {document.id} chunked into {len(chunks)} pieces")
        return chunks

    async def process_document(self, document: Document) -> None:
        """Process a single document through the full pipeline.

        Args:
            document: Document to process
        """
        logger.info(f"Processing document: {document.id}")

        # 1. Chunk the document
        chunks = self.chunk_document(document)

        if not chunks:
            logger.warning(f"No chunks generated for document: {document.id}")
            return

        # 2. Generate embeddings
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embedding_service.embed_texts(texts)

        # 3. Store in vector database
        await self.vector_store.store_embeddings(chunks, embeddings)

        logger.info(f"Document {document.id} processed successfully")

    async def process_documents(
        self, documents: AsyncGenerator[Document, None]
    ) -> None:
        """Process multiple documents through the pipeline.

        Args:
            documents: Async generator of documents to process
        """
        # Ensure vector store collection exists
        embedding_dim = self.embedding_service.get_embedding_dimension()
        await self.vector_store.ensure_collection(embedding_dim)

        processed_count = 0
        async for document in documents:
            try:
                await self.process_document(document)
                processed_count += 1

                if processed_count % 10 == 0:
                    logger.info(f"Processed {processed_count} documents")

            except Exception as e:
                logger.error(f"Error processing document {document.id}: {e}")
                continue

        logger.info(f"Finished processing {processed_count} documents")

    async def search_documents(self, query: str, limit: int = 10) -> List[dict]:
        """Search for documents similar to the query.

        Args:
            query: Search query text
            limit: Maximum number of results

        Returns:
            List of search results
        """
        # Generate embedding for the query
        query_embedding = self.embedding_service.embed_text(query)

        # Search in vector store
        results = await self.vector_store.search_similar(
            query_embedding, limit=limit, score_threshold=0.3
        )

        logger.info(f"Search query '{query}' returned {len(results)} results")
        return results
