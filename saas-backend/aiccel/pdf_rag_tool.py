import asyncio
import logging
import os
from typing import Any

import PyPDF2
from chromadb import PersistentClient
from textsplitter import TextSplitter

from .embeddings import EmbeddingProvider
from .providers import LLMProvider
from .tools import ParameterSchema, ParameterType, Tool


# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PDFRAGTool(Tool):
    """Tool for Retrieval-Augmented Generation (RAG) using PDF documents."""

    def __init__(
        self,
        base_pdf_folder: str,
        base_vector_db_path: str,
        embedding_provider: EmbeddingProvider,
        llm_provider: LLMProvider,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        k_value: int = 3
    ):
        self.base_pdf_folder = base_pdf_folder
        self.base_vector_db_path = base_vector_db_path
        self.embedding_provider = embedding_provider
        self.llm_provider = llm_provider
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.k_value = k_value
        self.text_splitter = TextSplitter()

        capabilities = [
            "pdf", "document", "retrieval", "rag", "information extraction",
            "file search", "document analysis", "text retrieval"
        ]

        super().__init__(
            name="pdf_rag",
            description="Retrieve and generate answers from PDF documents using RAG",
            executor=self._execute_rag,
            parameters=[
                ParameterSchema(
                    name="query",
                    type=ParameterType.STRING,
                    description="The question or query to answer based on PDF documents",
                    required=True
                )
            ]
        )

        self.set_llm_provider(llm_provider)
        self.detection_threshold = 0.4

        self.capability_keywords = capabilities  # Store capabilities as instance variable
        self.add_example({"name": "pdf_rag", "args": {"query": "What is the main topic of the document?"}})
        self.add_example({"name": "pdf_rag", "args": {"query": "Summarize the key points in the PDF"}})
        logger.debug("Initialized PDFRAGTool with base_pdf_folder=%s, base_vector_db_path=%s", base_pdf_folder, base_vector_db_path)

    def _get_or_create_vectorstore(self):
        logger.debug("Creating or retrieving vector store at %s", self.base_vector_db_path)
        try:
            client = PersistentClient(path=self.base_vector_db_path)

            # Wrapper for aiccel's embedding provider to work with Chroma
            class EmbeddingWrapper:
                def __init__(self, provider: EmbeddingProvider):
                    self.provider = provider

                def __call__(self, input: list[str]) -> list[list[float]]:
                    logger.debug("Generating embeddings for %d texts", len(input))
                    embeddings = self.provider.embed(input)
                    logger.debug("Generated %d embeddings", len(embeddings))
                    return embeddings

            embedding_function = EmbeddingWrapper(self.embedding_provider)
            collection = client.get_or_create_collection(
                name="pdf_documents",
                embedding_function=embedding_function
            )
            logger.debug("Vector store collection 'pdf_documents' ready")
            return collection
        except Exception as e:
            logger.error("Failed to create or retrieve vector store: %s", str(e))
            raise

    def _chunk_text(self, text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        logger.debug("Chunking text of length %d with chunk_size=%d, chunk_overlap=%d", len(text), chunk_size, chunk_overlap)
        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = min(start + chunk_size, text_length)
            # Adjust end to avoid splitting mid-word
            while end < text_length and text[end] not in [" ", "\n", ".", "!", "?"]:
                end -= 1
            if end == start:
                end = min(start + chunk_size, text_length)
            chunks.append(text[start:end])
            start += chunk_size - chunk_overlap
            if start >= text_length:
                break
        logger.debug("Created %d chunks", len(chunks))
        return chunks

    def _process_pdf_documents(self, pdf_folder: str, vectorstore):
        logger.debug("Processing PDFs in folder: %s", pdf_folder)
        if not os.path.exists(pdf_folder):
            logger.warning("PDF folder %s does not exist", pdf_folder)
            return f"Error: PDF folder {pdf_folder} does not exist."

        pdf_files = [f for f in os.listdir(pdf_folder) if f.endswith(".pdf")]
        logger.debug("Found %d PDF files: %s", len(pdf_files), pdf_files)

        # Get existing document IDs from vector store
        existing_ids = set(vectorstore.get()['ids'])
        logger.debug("Found %d existing document IDs in vector store", len(existing_ids))

        for filename in pdf_files:
            # Check if PDF is already processed by looking for its first chunk ID
            sample_id = f"{filename}_0"
            if sample_id in existing_ids:
                logger.debug("Skipping %s: already processed (ID %s found)", filename, sample_id)
                continue

            file_path = os.path.join(pdf_folder, filename)
            logger.debug("Processing PDF: %s", file_path)
            try:
                documents = self._load_pdf_documents(file_path)
                logger.debug("Loaded %d pages from %s", len(documents), filename)
                if not documents:
                    logger.warning("No text extracted from %s", filename)
                    continue
                category = self._categorize_document(documents, filename)
                logger.debug("Categorized %s as: %s", filename, category)
                combined_text = "\n\n".join(documents)
                texts = self._chunk_text(combined_text, self.chunk_size, self.chunk_overlap)
                logger.debug("Split %s into %d chunks", filename, len(texts))
                metadatas = [{"source": filename, "category": category} for _ in texts]
                ids = [f"{filename}_{i}" for i in range(len(texts))]

                # Add texts to Chroma collection
                logger.debug("Adding %d chunks to vector store for %s", len(texts), filename)
                vectorstore.add(
                    documents=texts,
                    metadatas=metadatas,
                    ids=ids
                )
                logger.debug("Successfully added chunks for %s to vector store", filename)
            except Exception as e:
                logger.error("Error processing %s: %s", filename, str(e))
                return f"Error processing {filename}: {e!s}"
        logger.debug("Processed all PDF documents successfully")
        return "Processed all PDF documents successfully."

    def _load_pdf_documents(self, filepath: str) -> list[str]:
        logger.debug("Loading PDF: %s", filepath)
        try:
            with open(filepath, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                pages = [page.extract_text() for page in pdf_reader.pages if page.extract_text()]
                logger.debug("Extracted text from %d pages in %s", len(pages), filepath)
                return pages
        except Exception as e:
            logger.error("Error loading PDF %s: %s", filepath, str(e))
            return []

    def _categorize_document(self, documents: list[str], filename: str) -> str:
        logger.debug("Categorizing document: %s", filename)
        content = "\n".join(documents[:3])[:1000]
        prompt = (
            f"Given the following content from a document, determine the main category it belongs to.\n"
            f"Document filename: {filename}\n"
            f"Content preview: {content}...\n"
            f"Category:"
        )
        try:
            category = self.llm_provider.generate(prompt).strip()
            logger.debug("Category for %s: %s", filename, category)
            return category
        except Exception as e:
            logger.error("Error categorizing %s: %s", filename, str(e))
            return "Uncategorized"

    def _execute_rag(self, args: dict[str, Any]) -> str:
        logger.debug("Executing RAG with args: %s", args)
        query = args.get("query")

        if not query:
            logger.warning("No query provided")
            return "Error: No query provided."

        try:
            # Get or create vectorstore
            vectorstore = self._get_or_create_vectorstore()

            # Process PDFs if folder exists
            if os.path.exists(self.base_pdf_folder):
                result = self._process_pdf_documents(self.base_pdf_folder, vectorstore)
                logger.debug("PDF processing result: %s", result)
            else:
                logger.warning("PDF folder %s does not exist", self.base_pdf_folder)

            # Query vectorstore
            logger.debug("Querying vector store with query: %s", query)
            results = vectorstore.query(
                query_texts=[query],
                n_results=self.k_value
            )
            logger.debug("Vector store query returned %d documents", len(results['documents'][0]) if results['documents'] else 0)

            if not results['documents'] or not results['documents'][0]:
                logger.warning("No relevant information found in the PDF documents")
                return "No relevant information found in the PDF documents."

            # Format context and sources
            context = "\n\n".join(results['documents'][0])
            sources = [f"Source: {meta['source']} (Category: {meta['category']})"
                      for meta in results['metadatas'][0]]
            logger.debug("Retrieved context and %d sources", len(sources))

            # Generate answer using LLM
            prompt = (
                f"Instructions: Provide a concise and accurate answer to the query based on the provided context.\n\n"
                f"Query: {query}\n\n"
                f"Context:\n{context}\n\n"
                f"Sources:\n" + "\n".join(sources) + "\n\n"
                "Answer:"
            )
            logger.debug("Generating answer with LLM")
            answer = self.llm_provider.generate(prompt).strip()
            logger.debug("Generated answer: %s", answer)

            # Combine answer with sources
            return f"{answer}\n\nSources:\n" + "\n".join(sources)

        except Exception as e:
            logger.error("Error executing PDF RAG: %s", str(e))
            return f"Error executing PDF RAG: {e!s}"

    async def execute_async(self, args: dict[str, Any]) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._execute_rag, args)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": list(self.capability_keywords),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question or query to answer based on PDF documents"
                    }
                },
                "required": ["query"]
            }
        }
