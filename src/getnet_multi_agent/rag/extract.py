"""HTML -> structured docs. Drops page chrome and text repeated across pages of a host."""

from collections import Counter
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

DROP = ["script", "style", "nav", "header", "footer", "noscript", "svg", "form", "head"]
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
BLOCKS = HEADINGS | {
    "p", "div", "li", "ul", "ol", "table", "section", "article", "aside", "main", "dl", "dt",
    "dd", "details", "summary", "blockquote", "tr", "td", "th", "tbody", "thead", "figure",
    "figcaption", "pre", "address",
}
BOILERPLATE_SHARE = 0.30
MAX_QUESTION_CHARS = 200
MAX_CARD_CHARS = 1000


@dataclass
class Doc:
    url: str
    host: str
    title: str
    blocks: list[tuple[str, str, str]] = field(default_factory=list)  # (heading, kind, text)


@dataclass
class _Unit:
    text: str
    is_heading: bool = False
    group: tuple[str, int] | None = None  # ("table" | "card", id)


def _norm(text: str) -> str:
    return " ".join(text.split())


class _Walker:
    def __init__(self):
        self.units: list[_Unit] = []
        self._gid = 0

    def _add(self, text, is_heading=False, group=None):
        text = _norm(text)
        if text:
            self.units.append(_Unit(text, is_heading, group))

    def walk(self, el: Tag, group=None):
        for ch in el.children:
            if isinstance(ch, NavigableString):
                if type(ch) is NavigableString:
                    self._add(str(ch), group=group)
                continue
            if not isinstance(ch, Tag):
                continue
            name = ch.name
            if name == "table" and group is None and ch.find("tr"):
                self._gid += 1
                for tr in ch.find_all("tr"):
                    cells = [_norm(c.get_text(" ")) for c in tr.find_all(["td", "th"])]
                    self._add(" | ".join(c for c in cells if c), group=("table", self._gid))
            elif name in HEADINGS:
                self._add(ch.get_text(" "), is_heading=group is None, group=group)
            elif ch.find(BLOCKS):
                if group is None and any("card" in c.lower() for c in ch.get("class", [])):
                    self._gid += 1
                    start = len(self.units)
                    self.walk(ch, ("card", self._gid))
                    if sum(len(u.text) for u in self.units[start:]) > MAX_CARD_CHARS:
                        del self.units[start:]  # a layout wrapper, not a product card
                        self.walk(ch, group)
                else:
                    self.walk(ch, group)
            else:
                text = _norm(ch.get_text(" "))
                question = text.endswith("?") and len(text) <= MAX_QUESTION_CHARS
                self._add(text, is_heading=question and group is None, group=group)


def _parse(page) -> tuple[str, list[_Unit]]:
    soup = BeautifulSoup(page.html, "lxml")
    title = _norm(soup.title.get_text()) if soup.title else ""
    h1 = soup.find("h1")
    title = title or (_norm(h1.get_text()) if h1 else "")
    for t in soup(DROP):
        t.decompose()
    w = _Walker()
    if soup.body:
        w.walk(soup.body)
    return title, w.units


def _assemble(units: list[_Unit]) -> list[tuple[str, str, str]]:
    blocks: list[tuple[str, str, str]] = []
    heading, has_body = "", True
    group, buf = None, []

    def flush():
        nonlocal group, buf, has_body
        if group and buf:
            kind = group[0]
            blocks.append((heading, kind, "\n".join(buf)))
            has_body = True
        group, buf = None, []

    def close_heading():
        if heading and not has_body:
            blocks.append((heading, "faq" if heading.endswith("?") else "section", heading))

    for u in units:
        if u.group:
            if u.group != group:
                flush()
                group = u.group
            buf.append(u.text)
        elif u.text == heading:
            continue  # accordion markup repeats the question
        elif u.is_heading:
            flush()
            close_heading()
            heading, has_body = u.text, False
        else:
            flush()
            kind = "faq" if heading.endswith("?") else "section"
            blocks.append((heading, kind, u.text))
            has_body = True
    flush()
    close_heading()
    return blocks


def extract_pages(pages) -> list[Doc]:
    parsed = [(p, *_parse(p)) for p in pages]
    host_pages: Counter = Counter(p.host for p, _, _ in parsed)
    freq: Counter = Counter()
    for p, _, units in parsed:
        for text in {u.text for u in units}:
            freq[(p.host, text)] += 1
    docs = []
    for p, title, units in parsed:
        n = host_pages[p.host]
        kept = [
            u for u in units
            if not (freq[(p.host, u.text)] >= 2 and freq[(p.host, u.text)] / n >= BOILERPLATE_SHARE)
        ]
        docs.append(Doc(p.url, p.host, title, _assemble(kept)))
    return docs
