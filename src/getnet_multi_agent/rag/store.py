"""Chroma persistent store (cosine HNSW) at DATA_DIR/state/chroma."""

import hashlib

import chromadb
from chromadb.config import Settings as ChromaSettings

COLLECTION = "getnet_kb"
META_KEYS = ("url", "site", "title", "heading", "kind", "is_rule")


def _client(settings):
    return chromadb.PersistentClient(
        path=str(settings.state_path / "chroma"),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def collection_name(settings) -> str:
    """Stub (hash) and live (Gemini) embeddings never share a collection."""
    return COLLECTION if settings.LLM_MODE == "live" else f"{COLLECTION}_stub"


def get_collection(settings):
    return _client(settings).get_or_create_collection(
        collection_name(settings), configuration={"hnsw": {"space": "cosine"}}, embedding_function=None
    )


def count(settings) -> int:
    try:
        return get_collection(settings).count()
    except Exception:
        return 0


def reset(settings):
    client = _client(settings)
    try:
        client.delete_collection(collection_name(settings))
    except Exception:
        pass
    return get_collection(settings)


def add_chunks(collection, chunks: list[dict], embeddings: list[list[float]]) -> None:
    collection.add(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        embeddings=embeddings,
        metadatas=[
            {**{k: c[k] for k in META_KEYS}, "text_hash": hashlib.sha256(c["text"].encode()).hexdigest()}
            for c in chunks
        ],
    )


def query(collection, embedding: list[float], n: int) -> dict:
    n = max(1, min(n, collection.count() or 1))
    return collection.query(
        query_embeddings=[embedding], n_results=n, include=["documents", "metadatas", "distances"]
    )
