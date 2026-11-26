import json
import shutil
import socket

import pytest

from getnet_multi_agent.core.settings import Settings
from getnet_multi_agent.rag import store
from getnet_multi_agent.rag.cache import cache_key, normalize_url, read_cache
from getnet_multi_agent.rag.ingest import ingest
from tests.conftest import FakeLLM

REQUIRED = [
    "https://site.getnet.com.br/duvidas/",
    "https://site.getnet.com.br/crediario/",
    "https://site.getnet.com.br/link-de-pagamento/",
    "https://site.getnet.com.br/pix/",
    "https://site.getnet.com.br/todas-as-maquininhas/",
    "https://www.getnet.net/en/our-solutions/in-person-payments",
]


@pytest.fixture(scope="module")
def ingested(tmp_path_factory):
    from tests.conftest import ROOT

    data = tmp_path_factory.mktemp("kb")
    s = Settings(_env_file=None, DATA_DIR=str(data), LLM_MODE="stub")
    llm = FakeLLM()
    mp = pytest.MonkeyPatch()

    def no_net(*a, **k):
        raise AssertionError("network access attempted")

    mp.setattr(socket.socket, "connect", no_net)
    try:
        n = ingest(s, llm, cache_dir=ROOT / "data" / "crawl_cache")
    finally:
        mp.undo()
    return s, llm, n


def test_fr_011_ingest_offline_status_200_html_only(ingested, crawl_cache_dir):
    s, _, n = ingested
    assert n > 100 and store.count(s) == n
    pages = read_cache(crawl_cache_dir)
    urls = [normalize_url(p.url) for p in pages]
    assert len(urls) == len(set(urls))  # deduped
    for meta_file in crawl_cache_dir.glob("*.json"):
        meta = json.loads(meta_file.read_text())
        if meta["status"] != 200:
            assert normalize_url(meta["final_url"]) not in urls


def test_fr_011_read_cache_filters_and_dedupes(tmp_path):
    from getnet_multi_agent.rag.cache import write_entry

    html = "<html><body><p>same visible text</p></body></html>"
    write_entry(tmp_path, "https://a.com/x", "https://a.com/x", 200, "text/html", html)
    write_entry(tmp_path, "https://a.com/y", "https://a.com/y", 200, "text/html", html)  # same text
    write_entry(tmp_path, "https://a.com/z", "https://a.com/z", 404, "text/html", html)
    write_entry(tmp_path, "https://a.com/p", "https://a.com/p", 200, "application/pdf", "x")
    write_entry(tmp_path, "https://a.com/q", "https://a.com/q", 200, "text/html", "<p>other</p>")
    (tmp_path / "orphan.json").write_text(json.dumps({"status": 200, "url": "https://a.com/o"}))
    assert sorted(p.url for p in read_cache(tmp_path)) == ["https://a.com/q", "https://a.com/x"]


def test_fr_012_required_urls_present(ingested):
    s, _, _ = ingested
    metas = store.get_collection(s).get(include=["metadatas"])["metadatas"]
    urls = {normalize_url(m["url"]) for m in metas}
    for u in REQUIRED:
        assert normalize_url(u) in urls, u


def test_fr_013_cache_key_matches_file_name(crawl_cache_dir):
    url = "https://site.getnet.com.br/duvidas/"
    assert cache_key(url) == cache_key("https://site.getnet.com.br/duvidas?x=1#frag")
    assert normalize_url("https://Site.Getnet.com.br/") == "https://site.getnet.com.br/"
    assert (crawl_cache_dir / f"{cache_key(url)}.json").exists()
    assert (crawl_cache_dir / f"{cache_key(url)}.html").exists()


def test_fr_023_second_ingest_does_not_reembed(ingested, crawl_cache_dir):
    s, llm, n = ingested
    calls = llm.embed_calls
    assert calls >= 1
    assert ingest(s, llm, cache_dir=crawl_cache_dir) == n
    assert llm.embed_calls == calls


def test_fr_023_rebuild_reembeds(settings, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    from getnet_multi_agent.rag.cache import write_entry

    body = "<h2>Titulo</h2><p>Conteudo suficientemente longo para virar um chunk valido aqui.</p>"
    write_entry(cache, "https://a.com/x", "https://a.com/x", 200, "text/html", f"<body>{body}</body>")
    llm = FakeLLM()
    assert ingest(settings, llm, cache_dir=cache) == 1
    shutil.rmtree(cache)
    cache.mkdir()
    assert ingest(settings, llm, rebuild=True, cache_dir=cache) == 0
    assert store.count(settings) == 0
