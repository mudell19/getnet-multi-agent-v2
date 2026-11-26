"""Knowledge agent: grounded RAG answers and Google Search grounded web answers."""

import re

from getnet_multi_agent.agents.prompts.knowledge import RAG_SYSTEM, WEB_SYSTEM
from getnet_multi_agent.contracts import AgentResult, Evidence, Observation, RankedChunk, Step
from getnet_multi_agent.core.llm import LLMClient
from getnet_multi_agent.merchants import today_brt
from getnet_multi_agent.rag.retriever import retrieve

LANG = {"en": "English", "pt": "Brazilian Portuguese"}
_TOKEN = re.compile(r"\w+", re.UNICODE)


def excerpt(text: str, focus: str, width: int = 300) -> str:
    """Two non-overlapping windows of `text` sharing the most tokens with `focus` (numbers weigh
    more), so the facts used in the answer stay checkable in the trace evidence."""
    focus_tokens = {t for t in _TOKEN.findall(focus.lower()) if len(t) > 2 or t.isdigit()}
    if len(text) <= 2 * width:
        return text
    scored = []
    for start in range(0, len(text) - width + 1, 40):
        window = text[start:start + width].lower()
        scored.append((sum(3 if t.isdigit() else 1 for t in focus_tokens if t in window), -start))
    scored.sort(reverse=True)
    first = -scored[0][1]
    second = next((-st for _, st in scored[1:] if abs(-st - first) >= width), None)
    starts = sorted(x for x in (first, second) if x is not None)
    return " … ".join(text[x:x + width] for x in starts)


def _context(chunks: list[RankedChunk]) -> str:
    docs = [
        f'<doc id="{i}" site="{c.site}" url="{c.url}" heading="{c.heading[:80]}">\n{c.text[:1800]}\n</doc>'
        for i, c in enumerate(chunks)
    ]
    return "<context>\n" + "\n".join(docs) + "\n</context>"


def knowledge_rag(step: Step, lang: str, llm: LLMClient, settings) -> Observation:
    chunks = retrieve(settings, llm, step.query, mode="hybrid")
    if not chunks:
        return Observation(step_id=step.id, agent="knowledge", source="rag", status="no_grounding",
                           unanswered=[step.query], error="no chunk above similarity threshold")
    system = RAG_SYSTEM.format(today=today_brt().isoformat(), language=LANG.get(lang, "English"))
    res = llm.generate("knowledge", f"{_context(chunks)}\n\nQuestion: {step.query}",
                       schema=AgentResult, system=system)
    r: AgentResult = res.parsed
    cited = [chunks[int(i)] for i in r.cited_ids if str(i).isdigit() and int(i) < len(chunks)]
    focus = f"{step.query} {r.answer}"
    ordered = cited + [c for c in chunks if c not in cited]
    evidence = [Evidence(url=c.url, title=c.heading or c.title, score=round(c.score, 4),
                         excerpt=excerpt(c.text, focus)) for c in ordered]
    status = "answered" if r.grounded and cited else "no_grounding"
    if status == "answered" and r.unanswered:
        status = "partial"
    return Observation(
        step_id=step.id, agent="knowledge", source="rag", status=status,
        answer=r.answer if status != "no_grounding" else "",
        evidence=evidence, unanswered=r.unanswered or ([step.query] if status == "no_grounding" else []),
        data={"cited_urls": list(dict.fromkeys(c.url for c in cited)),
              "global_site": any(c.site == "global" for c in cited)},
        usage=[res.usage],
    )


def knowledge_web(step: Step, lang: str, llm: LLMClient, settings) -> Observation:
    system = WEB_SYSTEM.format(today=today_brt().isoformat(), language=LANG.get(lang, "English"))
    res = llm.generate("knowledge", step.query, search=True, system=system)
    answer = res.text.strip()
    evidence = [Evidence(url=g.uri, title=g.title, score=1.0, excerpt="") for g in res.grounding]
    status = "answered" if answer else "failed"
    return Observation(step_id=step.id, agent="knowledge", source="web", status=status, answer=answer,
                       evidence=evidence, usage=[res.usage],
                       data={"search_queries": res.search_queries},
                       unanswered=[] if answer else [step.query])
