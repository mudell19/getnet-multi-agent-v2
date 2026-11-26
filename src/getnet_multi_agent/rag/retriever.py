"""Hybrid retrieval: vector top 3k + glossary lexical candidates, rule/glossary boosts."""

import math

from getnet_multi_agent.contracts import RankedChunk
from getnet_multi_agent.rag import store
from getnet_multi_agent.rag.glossary import GROUPS, expand, matched_groups

GROUP_BOOST = 0.10
MAX_GROUP_BOOST = 0.20
RULE_BOOST = 0.10
LEXICAL_LIMIT = 50


def score_chunk(similarity: float, shared_groups: int, is_rule: bool, hybrid: bool = True) -> float:
    if not hybrid:
        return similarity
    return similarity + min(GROUP_BOOST * shared_groups, MAX_GROUP_BOOST) + (
        RULE_BOOST if is_rule else 0.0
    )


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _lexical(collection, groups: set[int]) -> dict:
    """Chunks whose text contains an alias of the query's glossary groups (bounded)."""
    terms: set[str] = set()
    for g in groups:
        for alias in GROUPS[g]:
            terms.update({alias, alias.capitalize(), alias.title(), alias.upper()})
    docs = [{"$contains": t} for t in sorted(terms)]
    where = docs[0] if len(docs) == 1 else {"$or": docs}
    return collection.get(
        where_document=where,
        limit=LEXICAL_LIMIT,
        include=["documents", "metadatas", "embeddings"],
    )


def _ranked(cid, doc, meta, similarity, score) -> RankedChunk:
    return RankedChunk(
        id=cid, url=meta["url"], title=meta.get("title", ""), heading=meta.get("heading", ""),
        text=doc, site=meta.get("site", "br"), kind=meta.get("kind", "section"),
        is_rule=bool(meta.get("is_rule", False)), similarity=similarity, score=score,
    )


def retrieve(
    settings, llm, query: str, mode: str = "hybrid", k: int | None = None
) -> list[RankedChunk]:
    k = k or settings.RAG_TOP_K
    hybrid = mode == "hybrid"
    collection = store.get_collection(settings)
    if collection.count() == 0:
        return []
    q_groups = matched_groups(query) if hybrid else set()
    q_emb = llm.embed([expand(query) if hybrid else query], "RETRIEVAL_QUERY")[0]

    res = store.query(collection, q_emb, 3 * k)
    cands: dict[str, tuple] = {}
    for cid, doc, meta, dist in zip(
        res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0], strict=True
    ):
        cands[cid] = (doc, meta, 1.0 - dist)
    if hybrid and q_groups:
        lex = _lexical(collection, q_groups)
        for cid, doc, meta, emb in zip(
            lex["ids"], lex["documents"], lex["metadatas"], lex["embeddings"], strict=True
        ):
            if cid not in cands and q_groups & matched_groups(doc):
                cands[cid] = (doc, meta, _cosine(q_emb, emb))

    out = []
    for cid, (doc, meta, sim) in cands.items():
        shared = len(q_groups & matched_groups(doc)) if hybrid else 0
        score = score_chunk(sim, shared, bool(meta.get("is_rule")), hybrid)
        if score >= settings.RAG_MIN_SIMILARITY:
            out.append(_ranked(cid, doc, meta, sim, score))
    out.sort(key=lambda c: c.score, reverse=True)
    return out[:k]
