"""Deterministic offline LLMClient (LLM_MODE=stub): no network, keyword-heuristic planner."""

from pydantic import BaseModel

from getnet_multi_agent.contracts import Plan, Step, Usage
from getnet_multi_agent.core import request_context
from getnet_multi_agent.core.llm import (
    EmbedTaskType,
    GroundingSource,
    LLMResult,
    Message,
    Task,
    ToolSpec,
    hash_embedding,
)

_WEB = ("weather", "clima", "tempo", "exchange", "câmbio", "cambio", "cotação", "cotacao",
        "euro", "dólar", "dolar", "news")
_SUPPORT = ("sales", "vendas", "deposit", "receb", "terminal", "maquininha", "machine",
            "decline", "connect")
_RAG_EXTRA = ("advance", "antecipação", "antecipacao", "how does")
_PT = ("ã", "ç", "é", " o ", " de ", "você", "minha")


def _last_user_text(contents: str | list[Message]) -> str:
    if isinstance(contents, str):
        return contents
    for m in reversed(contents):
        if m.role == "user":
            return m.text
    return ""


def _plan(text: str) -> Plan:
    low = f" {text.lower()} "
    lang = "pt" if any(m in low for m in _PT) else "en"
    steps: list[Step] = []
    if any(w in low for w in _WEB):
        steps.append(Step(id="s1", agent="knowledge", source="web", query=text))
    elif any(w in low for w in _SUPPORT):
        steps.append(Step(id="s1", agent="support", query=text))
        if any(w in low for w in _RAG_EXTRA):
            steps.append(Step(id="s2", agent="knowledge", source="rag", query=text))
    else:
        steps.append(Step(id="s1", agent="knowledge", source="rag", query=text))
    return Plan(steps=steps, lang=lang, standalone=text, parts=[text])


def _default_instance(schema: type[BaseModel], text: str) -> BaseModel:
    if schema is Plan:
        return _plan(text)
    fields = schema.model_fields
    defaults: dict = {}
    if "answer" in fields:
        defaults["answer"] = "[stub] answer based on the provided context."
    if "grounded" in fields:
        defaults["grounded"] = True
    if "complete" in fields:
        defaults["complete"] = True
    try:
        return schema.model_validate(defaults)
    except Exception:  # noqa: BLE001
        return schema.model_construct(**defaults)


class StubClient:
    def __init__(self, settings):
        self.s = settings

    def generate(
        self,
        task: Task,
        contents: str | list[Message],
        *,
        schema: type[BaseModel] | None = None,
        tools: list[ToolSpec] | None = None,
        search: bool = False,
        system: str | None = None,
    ) -> LLMResult:
        if search and tools:
            raise ValueError("search and tools cannot share a request")
        text = _last_user_text(contents)
        usage = Usage(
            model="stub", task=task, prompt_tokens=max(1, len(text) // 4), output_tokens=10
        )
        request_context.add_usage(usage)
        if schema is not None:
            parsed = _default_instance(schema, text)
            return LLMResult(text=parsed.model_dump_json(), parsed=parsed, usage=usage)
        result = LLMResult(text="[stub] " + text[:200], usage=usage)
        if search:
            result.grounding = [GroundingSource(title="stub", uri="https://example.com/stub")]
        return result

    def embed(self, texts: list[str], task_type: EmbedTaskType) -> list[list[float]]:
        return [hash_embedding(t) for t in texts]
