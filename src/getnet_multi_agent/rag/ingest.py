"""Offline ingestion: crawl cache -> chunks -> embeddings -> Chroma. Never touches the network."""

from pathlib import Path

from getnet_multi_agent.core.request_context import start_request
from getnet_multi_agent.rag import store
from getnet_multi_agent.rag.cache import read_cache
from getnet_multi_agent.rag.chunk import chunk_docs
from getnet_multi_agent.rag.extract import extract_pages

BATCH = 100


def ingest(settings, llm, rebuild: bool = False, cache_dir: Path | None = None) -> int:
    existing = store.count(settings)
    if existing and not rebuild:
        return existing
    cache_dir = Path(cache_dir) if cache_dir else settings.data_path / "crawl_cache"
    chunks = chunk_docs(extract_pages(read_cache(cache_dir)))
    collection = store.reset(settings) if rebuild else store.get_collection(settings)
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i : i + BATCH]
        start_request()  # ingestion is not a user request: the per-request budget applies per batch
        embeddings = llm.embed([c["text"] for c in batch], "RETRIEVAL_DOCUMENT")
        store.add_chunks(collection, batch, embeddings)
    return len(chunks)
