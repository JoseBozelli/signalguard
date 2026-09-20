"""
Chroma-backed retrieval index for SignalGuard.

Embeddings are computed externally (via an Embedder) and passed to Chroma
explicitly -- the collection is never given Chroma's built-in
embedding_function, so swapping VoyageEmbedder <-> FakeEmbedder never
requires touching this module. Distance space is explicitly set to
cosine: Voyage embeddings are normalized (length 1) per Voyage's own
docs, and cosine is the correct similarity measure for normalized text
embeddings regardless of provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import chromadb

from signalguard.rag.chunking import chunk_corpus
from signalguard.rag.embeddings import Embedder

COLLECTION_NAME = "signalguard_docs"


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: str
    score: float  # cosine similarity; higher = more relevant
    source_file: str
    heading: str
    text: str


def build_index(
    docs_dir: Path,
    embedder: Embedder,
    persist_directory: Optional[str] = None,
    collection_name: str = COLLECTION_NAME,
):
    """Chunk the corpus, embed every chunk, and load it into a fresh Chroma collection."""
    client = chromadb.PersistentClient(path=persist_directory) if persist_directory else chromadb.Client()

    # Fresh collection every build -- avoids stale entries from a prior run
    # silently mixing into retrieval/eval results.
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})

    chunks = chunk_corpus(docs_dir)
    if not chunks:
        raise ValueError(f"No chunks found in {docs_dir} -- check the corpus exists and uses ## headings.")

    embeddings = embedder.embed_documents([c.text for c in chunks])

    collection.add(
        ids=[c.chunk_id for c in chunks],
        embeddings=embeddings,
        documents=[c.text for c in chunks],
        metadatas=[{"source_file": c.source_file, "heading": c.heading} for c in chunks],
    )

    return collection


def retrieve(collection, query: str, embedder: Embedder, k: int = 3) -> List[RetrievalResult]:
    """Retrieve the top-k most relevant chunks for a query."""
    query_embedding = embedder.embed_query(query)
    results = collection.query(query_embeddings=[query_embedding], n_results=k)

    retrieved: List[RetrievalResult] = []
    ids = results["ids"][0]
    distances = results["distances"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]

    for chunk_id, distance, document, metadata in zip(ids, distances, documents, metadatas):
        # With hnsw:space="cosine", Chroma's distance is (1 - cosine_similarity),
        # so similarity is just the inverse of that.
        score = 1.0 - distance
        retrieved.append(
            RetrievalResult(
                chunk_id=chunk_id,
                score=score,
                source_file=metadata["source_file"],
                heading=metadata["heading"],
                text=document,
            )
        )

    return retrieved