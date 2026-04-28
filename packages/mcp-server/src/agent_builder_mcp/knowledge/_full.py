"""Knowledge base setup and management."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import chromadb
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.vector_stores.chroma import ChromaVectorStore

from .loaders import load_api_specs, load_markdown_docs

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
DEV_GUIDE_PATH = DATA_DIR / "dev_guide.md"
AGENTIC_API_SPEC_PATH = DATA_DIR / "agentic_api.json"
REGISTRY_API_SPEC_PATH = DATA_DIR / "registry_api.json"
SDK_DOCS_PATH = DATA_DIR / "sdk_docs.json"

_index = None
_documents = None


def setup_kb() -> VectorStoreIndex:
    """Initialize knowledge base with all sources."""
    global _index, _documents
    if _index is not None:
        logger.debug("Returning cached knowledge base index")
        return _index

    logger.info("Setting up knowledge base - downloading HuggingFace embedding model")
    logger.info("Model: intfloat/e5-base-v2")

    # Log cache location
    import os

    cache_dir = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    logger.debug(f"HuggingFace cache directory: {cache_dir}")

    start_time = time.time()
    logger.info("Downloading/loading embedding model (this may take time on first run)...")

    Settings.embed_model = HuggingFaceEmbedding(model_name="intfloat/e5-base-v2")

    download_time = time.time() - start_time
    logger.info(f"Embedding model loaded in {download_time:.2f} seconds")

    logger.debug("Setting up node parser with chunk_size=512, overlap=50")
    Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)

    logger.info("Loading documentation sources")
    documents = []

    logger.debug(f"Loading markdown docs from {DEV_GUIDE_PATH}")
    documents.extend(load_markdown_docs(str(DEV_GUIDE_PATH)))

    # Load pre-extracted SDK docs
    logger.debug(f"Loading SDK docs from {SDK_DOCS_PATH}")
    with open(SDK_DOCS_PATH) as f:
        sdk_data = json.load(f)
    logger.debug(f"Loaded {len(sdk_data)} SDK documentation entries")
    for item in sdk_data:
        doc_text = f"# {item['name']}\n\n{item['docstring']}"
        documents.append(Document(text=doc_text, metadata={"source": "sdk", "name": item["name"]}))

    logger.debug(f"Loading Agentic API specs from {AGENTIC_API_SPEC_PATH}")
    documents.extend(load_api_specs(str(AGENTIC_API_SPEC_PATH)))

    logger.debug(f"Loading Registry API specs from {REGISTRY_API_SPEC_PATH}")
    documents.extend(load_api_specs(str(REGISTRY_API_SPEC_PATH)))

    logger.info(f"Loaded {len(documents)} total documents")

    logger.debug("Creating ChromaDB ephemeral client")
    chroma_client = chromadb.EphemeralClient()
    chroma_collection = chroma_client.create_collection("atx_docs")
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

    logger.info("Building vector store index from documents")
    index_start = time.time()
    _index = VectorStoreIndex.from_documents(documents, vector_store=vector_store)
    index_time = time.time() - index_start
    logger.info(f"Vector index built in {index_time:.2f} seconds")

    _documents = documents  # Store for BM25 retriever

    total_time = time.time() - start_time
    logger.info(f"Knowledge base setup complete in {total_time:.2f} seconds")

    return _index


def get_index() -> VectorStoreIndex:
    """Get or create the knowledge base index."""
    return setup_kb()


def get_hybrid_retriever(top_k: int = 5):
    """Get hybrid retriever combining BM25 and embedding search."""
    global _documents
    index = get_index()

    # Ensure documents are loaded
    if _documents is None:
        setup_kb()

    # Create vector retriever
    vector_retriever = index.as_retriever(similarity_top_k=top_k)

    # Create BM25 retriever from documents
    bm25_retriever = BM25Retriever.from_defaults(nodes=_documents, similarity_top_k=top_k)

    return _HybridRetriever(vector_retriever, bm25_retriever, top_k)


class _HybridRetriever:
    """Simple hybrid retriever with reciprocal rank fusion (no LLM required)."""

    def __init__(self, vector_retriever, bm25_retriever, top_k: int = 5):
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.top_k = top_k

    def retrieve(self, query: str):
        """Retrieve using both retrievers and fuse with RRF."""
        vector_nodes = self.vector_retriever.retrieve(query)
        bm25_nodes = self.bm25_retriever.retrieve(query)

        # Reciprocal Rank Fusion
        k = 60  # RRF constant
        scores: dict[int, float] = {}
        node_map: dict[int, Any] = {}

        for rank, node in enumerate(vector_nodes):
            node_id = id(node)
            scores[node_id] = scores.get(node_id, 0) + 1 / (k + rank + 1)
            node_map[node_id] = node

        for rank, node in enumerate(bm25_nodes):
            node_id = id(node)
            scores[node_id] = scores.get(node_id, 0) + 1 / (k + rank + 1)
            node_map[node_id] = node

        # Sort by fused score and return top_k
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        results = []
        for node_id in sorted_ids[: self.top_k]:
            node = node_map[node_id]
            node.score = scores[node_id]
            results.append(node)

        return results
