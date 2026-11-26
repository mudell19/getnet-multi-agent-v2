"""Crawl cache: `<sha256(normalized_url)>.json` metadata + `<same>.html` raw HTML."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup


@dataclass
class Page:
    url: str
    html: str
    host: str


def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    path = p.path.rstrip("/") or "/"
    return f"{p.scheme.lower()}://{p.netloc.lower()}{path}"


def cache_key(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


def write_entry(
    cache_dir: Path, url: str, final_url: str, status: int, content_type: str, html: str
) -> None:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = cache_key(url)
    meta = {"url": url, "final_url": final_url, "status": status, "content_type": content_type}
    (cache_dir / f"{key}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (cache_dir / f"{key}.html").write_text(html, encoding="utf-8")


def _visible_hash(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    text = " ".join(soup.get_text(" ").split())
    return hashlib.sha256(text.encode()).hexdigest()


def read_cache(cache_dir: Path) -> list[Page]:
    """Pages with status 200 and text/html; deduped by final URL and by visible-text hash."""
    pages: list[Page] = []
    seen_urls: set[str] = set()
    seen_text: set[str] = set()
    for meta_file in sorted(Path(cache_dir).glob("*.json")):
        html_file = meta_file.with_suffix(".html")
        if not html_file.exists():
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if meta.get("status") != 200 or "text/html" not in (meta.get("content_type") or ""):
            continue
        url = meta.get("final_url") or meta["url"]
        norm = normalize_url(url)
        if norm in seen_urls:
            continue
        html = html_file.read_text(encoding="utf-8", errors="replace")
        digest = _visible_hash(html)
        if digest in seen_text:
            continue
        seen_urls.add(norm)
        seen_text.add(digest)
        pages.append(Page(url=url, html=html, host=urlsplit(url).netloc.lower()))
    return pages
