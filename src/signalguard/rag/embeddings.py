"""
Embedding providers for SignalGuard RAG.

Embedding is behind a small interface (`Embedder`) rather than a single
hardcoded implementation for one reason: tests and the evaluation
harness must be able to run without hitting a paid API. Tests use
`FakeEmbedder` (deterministic, no network, no API key required);
production code uses `VoyageEmbedder`.

Voyage's API distinguishes document embeddings from query embeddings
(`input_type="document"` vs `input_type="query"`) for better asymmetric
retrieval quality. Both implementations preserve that distinction in
their method signatures, even though FakeEmbedder doesn't need it, so
swapping providers never silently changes calling behavior.
"""

from __future__ import annotations

import hashlib
import os
import struct
from typing import List, Protocol

VOYAGE_MODEL = "voyage-4-lite"
EMBEDDING_DIM = 1024


class Embedder(Protocol):
    def embed_documents(self, texts: List[str]) -> List[List[float]]: ...
    def embed_query(self, text: str) -> List[float]: ...


class VoyageEmbedder:
    """Real embedder backed by the Voyage AI API. Reads the key from .secrets."""

    def __init__(self, model: str = VOYAGE_MODEL, secrets_path: str = ".secrets"):
        from dotenv import load_dotenv
        import voyageai

        load_dotenv(secrets_path)
        self._client = voyageai.Client()
        self._model = model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        result = self._client.embed(texts, model=self._model, input_type="document")
        return result.embeddings

    def embed_query(self, text: str) -> List[float]:
        result = self._client.embed([text], model=self._model, input_type="query")
        return result.embeddings[0]


class FakeEmbedder:
    """
    Deterministic, network-free embedder for tests. NOT semantically
    meaningful -- it hashes text into a fixed-dimension unit vector, so it
    can only test index plumbing (add/query round-trips, chunk_id and
    metadata integrity), never actual retrieval quality. Retrieval-quality
    evaluation always runs against VoyageEmbedder, never this class.
    """

    def __init__(self, dim: int = EMBEDDING_DIM):
        self._dim = dim

    def _hash_vector(self, text: str) -> List[float]:
        raw: List[float] = []
        counter = 0
        while len(raw) < self._dim:
            digest = hashlib.sha256(f"{text}:{counter}".encode("utf-8")).digest()
            for i in range(0, len(digest) - 3, 4):
                if len(raw) >= self._dim:
                    break
                (val,) = struct.unpack(">I", digest[i : i + 4])
                raw.append((val / 0xFFFFFFFF) * 2 - 1)  # map to [-1, 1]
            counter += 1

        norm = sum(x * x for x in raw) ** 0.5
        return [x / norm for x in raw] if norm > 0 else raw

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._hash_vector(text)

# Registry of available providers. Adding a new one is: implement Embedder, add one line here -- mirrors the same
# patterns as llm/reasoner.py
_PROVIDERS = {"voyage": VoyageEmbedder}

def get_embedder(provider: Optional[str] = None, model: Optional[str] = None) -> Embedder:
    """
    Config-driven provider selection, same pattern as get_reasoner(). Reads SIGNALGUARD_EMBEDDING_PROVIDER /
    SIGNALGUARD_EMBEDDING_MODEL from the environment when not passed explicitly.
    """
    provider = provider or os.environ.get("SIGNALGUARD_EMBEDDING_PROVIDER", "voyage")
    if provider not in _PROVIDERS:
        raise ValueError(
            f"Unknown embedding provider '{provider}'. Available: {list(_PROVIDERS)}. "
            "To add another provider, implement the Embedder protocl and register it in _PROVIDERS."
        )

    kwargs = {}
    env_model = model or os.environ.get("SIGNALGUARD_EMBEDDING_MODEL")
    if env_model:
        kwargs["model"] = env_model

    return _PROVIDERS[provider](**kwargs)