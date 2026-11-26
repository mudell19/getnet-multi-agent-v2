"""Docs -> chunks by heading / FAQ question. Never fixed windows."""

import hashlib
import re

MAX_CHARS = 2500
MIN_CHARS = 40

_RULE = re.compile(
    r"\b(é necessário|necess[áa]rio|precisa|obrigat[óo]rio|exige|somente|apenas|até \d+"
    r"|required|must|need to|only)\b|\d+x\b",
    re.IGNORECASE,
)


def is_rule(text: str) -> bool:
    return bool(_RULE.search(text))


def _split(paras: list[str]) -> list[str]:
    out, cur, size = [], [], 0
    for p in paras:
        if cur and size + len(p) > MAX_CHARS:
            out.append("\n".join(cur))
            cur, size = [], 0
        cur.append(p)
        size += len(p) + 1
    if cur:
        out.append("\n".join(cur))
    return out


def chunk_docs(docs) -> list[dict]:
    chunks: list[dict] = []
    for doc in docs:
        site = "global" if doc.host == "www.getnet.net" else "br"
        ordinal = 0

        def emit(heading, kind, paras, doc=doc, site=site):
            nonlocal ordinal
            for body in _split(paras):
                text = body if body == heading or not heading else f"{heading}\n{body}"
                if len(text) < MIN_CHARS:
                    continue
                cid = hashlib.sha256(f"{doc.url}{heading}{ordinal}".encode()).hexdigest()[:32]
                ordinal += 1
                chunks.append({
                    "id": cid, "url": doc.url, "site": site, "title": doc.title,
                    "heading": heading, "kind": kind, "is_rule": is_rule(text), "text": text,
                })

        cur_heading, cur_paras = None, []
        for heading, kind, text in doc.blocks:
            if kind in ("table", "card"):
                if cur_paras:
                    emit(cur_heading, "faq" if cur_heading.endswith("?") else "section", cur_paras)
                    cur_heading, cur_paras = None, []
                emit(heading, kind, text.split("\n"))
                continue
            if heading != cur_heading and cur_paras:
                emit(cur_heading, "faq" if cur_heading.endswith("?") else "section", cur_paras)
                cur_paras = []
            cur_heading = heading
            cur_paras.append(text)
        if cur_paras:
            emit(cur_heading, "faq" if cur_heading.endswith("?") else "section", cur_paras)
    return chunks
