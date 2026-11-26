"""Refresh crawler (the only networked RAG module): start pages + their links, depth 1."""

import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx

from getnet_multi_agent.rag.cache import normalize_url, write_entry

START_PAGES = [
    "https://site.getnet.com.br/",
    "https://site.getnet.com.br/duvidas/",
    "https://site.getnet.com.br/crediario/",
    "https://site.getnet.com.br/link-de-pagamento/",
    "https://site.getnet.com.br/pix/",
    "https://site.getnet.com.br/todas-as-maquininhas/",
    "https://www.getnet.net/en",
    "https://www.getnet.net/en/our-solutions/in-person-payments",
]
SLEEP_S = 2
HEADERS = {"User-Agent": "getnet-multi-agent-kb-refresh/1.0"}


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def _allowed(url: str, host: str) -> bool:
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or p.netloc.lower() != host:
        return False
    if host == "www.getnet.net":
        return p.path == "/en" or p.path.startswith("/en/")
    return True


def _links(html: str, base: str, host: str) -> list[str]:
    parser = _Links()
    parser.feed(html)
    found = []
    for href in parser.hrefs:
        url = urldefrag(urljoin(base, href))[0]
        if _allowed(url, host):
            found.append(url)
    return found


def refresh(
    settings,
    max_pages: int | None = None,
    client: httpx.Client | None = None,
    sleep=time.sleep,
) -> int:
    cap = max_pages if max_pages is not None else settings.RAG_MAX_PAGES
    cache_dir = Path(settings.data_path) / "crawl_cache"
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=20.0, headers=HEADERS)
    written, requests = 0, 0
    blocked: set[str] = set()
    seen: set[str] = set()

    def fetch(url: str, host: str) -> str | None:
        """Fetch one URL; returns html when written, None otherwise."""
        nonlocal written, requests
        if requests:
            sleep(SLEEP_S)
        requests += 1
        try:
            resp = client.get(url, follow_redirects=True)
        except httpx.HTTPError:
            return None
        if resp.status_code in (403, 429):
            blocked.add(host)
            return None
        ctype = resp.headers.get("content-type", "")
        write_entry(cache_dir, url, str(resp.url), resp.status_code, ctype, resp.text)
        written += 1
        if resp.status_code == 200 and "text/html" in ctype:
            return resp.text
        return None

    try:
        queue: list[tuple[str, str]] = []
        for start in START_PAGES:
            host = urlsplit(start).netloc.lower()
            if written >= cap:
                break
            if host in blocked or normalize_url(start) in seen:
                continue
            seen.add(normalize_url(start))
            html = fetch(start, host)
            if html:
                for link in _links(html, start, host):
                    queue.append((link, host))
        for url, host in queue:
            if written >= cap:
                break
            if host in blocked or normalize_url(url) in seen:
                continue
            seen.add(normalize_url(url))
            fetch(url, host)
    finally:
        if own:
            client.close()
    return written
