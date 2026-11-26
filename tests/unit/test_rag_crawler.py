import json

import httpx

from getnet_multi_agent.rag.cache import cache_key
from getnet_multi_agent.rag.crawler import START_PAGES, refresh


def _html(*links):
    return "<html><body>" + "".join(f'<a href="{x}">l</a>' for x in links) + "</body></html>"


def _run(settings, handler, **kw):
    sleeps = []
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    n = refresh(settings, client=client, sleep=sleeps.append, **kw)
    return n, sleeps


def _site(requested, status_for=None):
    status_for = status_for or {}

    def handler(req: httpx.Request) -> httpx.Response:
        requested.append(str(req.url))
        status = status_for.get(str(req.url), 200)
        links = {
            "https://site.getnet.com.br/": _html("/a/", "https://other.com/x", "/b/#frag"),
            "https://site.getnet.com.br/a/": _html("/deep/"),
            "https://www.getnet.net/en": _html("/en/page", "/pt/page", "/careers"),
        }.get(str(req.url), "<html><body>x</body></html>")
        return httpx.Response(status, text=links, headers={"content-type": "text/html; charset=utf-8"})

    return handler


def test_fr_014_depth1_same_host_en_only(settings):
    requested: list[str] = []
    n, sleeps = _run(settings, _site(requested))
    assert set(START_PAGES) <= {u.rstrip("/") + ("/" if u.endswith("/") else "") for u in requested}
    assert "https://site.getnet.com.br/a/" in requested
    assert "https://site.getnet.com.br/b/" in requested
    assert "https://www.getnet.net/en/page" in requested
    assert "https://site.getnet.com.br/deep/" not in requested  # depth 2
    assert not any("other.com" in u for u in requested)
    assert not any(u.endswith("/pt/page") or u.endswith("/careers") for u in requested)
    assert n == len(requested)
    assert sleeps and set(sleeps) == {2} and len(sleeps) == len(requested) - 1


def test_fr_014_writes_cache_format(settings):
    _run(settings, _site([]), max_pages=1)
    cache = settings.data_path / "crawl_cache"
    key = cache_key("https://site.getnet.com.br/")
    meta = json.loads((cache / f"{key}.json").read_text())
    assert meta == {
        "url": "https://site.getnet.com.br/",
        "final_url": "https://site.getnet.com.br/",
        "status": 200,
        "content_type": "text/html; charset=utf-8",
    }
    assert "<a href" in (cache / f"{key}.html").read_text()


def test_fr_014_stops_host_on_403_and_429(settings):
    for code in (403, 429):
        requested: list[str] = []
        first = "https://site.getnet.com.br/"
        n, _ = _run(settings, _site(requested, {first: code}))
        br = [u for u in requested if "site.getnet.com.br" in u]
        assert br == [first]  # host stopped at its first block
        assert any("www.getnet.net" in u for u in requested)  # other host unaffected
        assert n == len(requested) - 1


def test_fr_014_respects_max_pages_and_follows_redirects(settings):
    requested: list[str] = []

    def handler(req):
        requested.append(str(req.url))
        if req.url.path == "/pix/":
            return httpx.Response(301, headers={"location": "https://site.getnet.com.br/pix-novo/"})
        return httpx.Response(200, text=_html(), headers={"content-type": "text/html"})

    n, _ = _run(settings, handler, max_pages=5)
    assert n == 5 and len(requested) == 6  # the redirect hop is one extra request
    cache = settings.data_path / "crawl_cache"
    meta = json.loads((cache / f"{cache_key('https://site.getnet.com.br/pix/')}.json").read_text())
    assert meta["final_url"] == "https://site.getnet.com.br/pix-novo/"
