"""Live LLMClient on google-genai (contracts verified in the 001 research.md)."""

import time
from collections.abc import Callable
from typing import Any

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from getnet_multi_agent.contracts import Usage
from getnet_multi_agent.core import metrics, request_context
from getnet_multi_agent.core.llm import (
    BudgetExceeded,
    EmbedTaskType,
    FunctionCall,
    GroundingSource,
    LLMResult,
    LLMUnavailable,
    Message,
    Task,
    ToolSpec,
)
from getnet_multi_agent.core.logging import get_logger

log = get_logger("getnet.llm")
_LITE_TASKS = {"router", "critic", "summary", "personality"}
_EMBED_BATCH = 100


class GeminiClient:
    def __init__(self, settings, client: Any = None, sleep: Callable[[float], None] = time.sleep):
        self.s = settings
        self._sleep = sleep
        self.client = client or genai.Client(
            api_key=settings.GEMINI_API_KEY.get_secret_value(),
            http_options=types.HttpOptions(timeout=int(settings.LLM_TIMEOUT_S * 1000)),
        )

    # -- helpers -------------------------------------------------------------------------
    def _route(self, task: Task) -> tuple[str, str, float, float]:
        s = self.s
        if task in _LITE_TASKS:
            return (s.GEMINI_ROUTER_MODEL, s.GEMINI_ROUTER_THINKING,
                    s.PRICE_LITE_INPUT_PER_M, s.PRICE_LITE_OUTPUT_PER_M)
        if task == "judge":
            return (s.GEMINI_JUDGE_MODEL, s.GEMINI_JUDGE_THINKING,
                    s.PRICE_FLASH_INPUT_PER_M, s.PRICE_FLASH_OUTPUT_PER_M)
        return (s.GEMINI_MODEL, s.GEMINI_MODEL_THINKING,
                s.PRICE_FLASH_INPUT_PER_M, s.PRICE_FLASH_OUTPUT_PER_M)

    @staticmethod
    def _contents(contents: str | list[Message]) -> Any:
        if isinstance(contents, str):
            return contents
        out = []
        for m in contents:
            if m.role == "tool":
                part = types.Part.from_function_response(
                    name=m.tool_name or "", response=m.tool_response or {}
                )
                out.append(types.Content(role="user", parts=[part]))
            elif m.role == "model" and m.raw is not None:
                out.append(m.raw)
            else:
                out.append(types.Content(role=m.role, parts=[types.Part(text=m.text)]))
        return out

    def _call(self, fn: Callable[[], Any]) -> Any:
        """One retry on 429/5xx; everything else becomes LLMUnavailable."""
        for attempt in (1, 2):
            try:
                return fn()
            except errors.APIError as e:
                retryable = e.code == 429 or (isinstance(e.code, int) and e.code >= 500)
                if attempt == 1 and retryable:
                    self._sleep(1.0)
                    continue
                raise LLMUnavailable(f"LLM error {e.code}") from e
            except httpx.TimeoutException as e:
                raise LLMUnavailable("LLM timeout") from e
            except Exception as e:  # noqa: BLE001 - any provider failure is "unavailable"
                raise LLMUnavailable(f"LLM failure: {type(e).__name__}") from e
        raise LLMUnavailable("LLM failure")  # pragma: no cover

    def _check_budget(self) -> None:
        if request_context.tokens_used() >= self.s.REQUEST_TOKEN_BUDGET:
            raise BudgetExceeded("request token budget spent")

    # -- API ---------------------------------------------------------------------------
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
        self._check_budget()
        model, level, p_in, p_out = self._route(task)
        cfg: dict[str, Any] = {
            "system_instruction": system,
            "thinking_config": types.ThinkingConfig(thinking_level=level),
        }
        if schema is not None:
            cfg["response_mime_type"] = "application/json"
            cfg["response_schema"] = schema
        if tools:
            decls = [
                types.FunctionDeclaration(
                    name=t.name, description=t.description, parameters_json_schema=t.parameters
                )
                for t in tools
            ]
            cfg["tools"] = [types.Tool(function_declarations=decls)]
            cfg["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
        if search:
            cfg["tools"] = [types.Tool(google_search=types.GoogleSearch())]
        config = types.GenerateContentConfig(**cfg)
        body = self._contents(contents)

        t0 = time.monotonic()
        resp = self._call(
            lambda: self.client.models.generate_content(model=model, contents=body, config=config)
        )
        latency = int((time.monotonic() - t0) * 1000)

        cand = (getattr(resp, "candidates", None) or [None])[0]
        try:
            text = resp.text or ""
        except Exception:  # noqa: BLE001 - e.g. only function-call parts
            text = ""
        calls = [
            FunctionCall(name=fc.name, args=dict(fc.args or {}))
            for fc in (getattr(resp, "function_calls", None) or [])
        ]
        gm = getattr(cand, "grounding_metadata", None)
        grounding = [
            GroundingSource(title=ch.web.title or "", uri=ch.web.uri)
            for ch in (getattr(gm, "grounding_chunks", None) or [])
            if getattr(ch, "web", None) and ch.web.uri
        ]
        queries = list(getattr(gm, "web_search_queries", None) or [])

        parsed = None
        if schema is not None:
            parsed = getattr(resp, "parsed", None)
            if parsed is None:
                try:
                    parsed = schema.model_validate_json(text)
                except Exception as e:  # noqa: BLE001
                    raise LLMUnavailable("unparseable structured output") from e

        um = getattr(resp, "usage_metadata", None)
        pt = getattr(um, "prompt_token_count", None) or 0
        ct = getattr(um, "candidates_token_count", None) or 0
        tt = getattr(um, "thoughts_token_count", None) or 0
        cost = (
            pt * p_in / 1e6 + (ct + tt) * p_out / 1e6
            + len(queries) * self.s.PRICE_SEARCH_PER_1K / 1000
        )
        usage = Usage(
            model=model, task=task, latency_ms=latency, prompt_tokens=pt, output_tokens=ct,
            thinking_tokens=tt, search_queries=len(queries), cost_usd=cost,
        )
        self._record(usage, "ok")
        return LLMResult(
            text=text, parsed=parsed, content=getattr(cand, "content", None),
            function_calls=calls, grounding=grounding, search_queries=queries, usage=usage,
        )

    def embed(self, texts: list[str], task_type: EmbedTaskType) -> list[list[float]]:
        model = self.s.GEMINI_EMBEDDING_MODEL
        cfg = types.EmbedContentConfig(task_type=task_type, output_dimensionality=768)
        out: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH):
            batch = texts[i : i + _EMBED_BATCH]
            self._check_budget()
            t0 = time.monotonic()
            resp = self._call(
                # One Content per text: a plain list of strings is embedded as ONE multi-part
                # content by gemini-embedding-2 (verified live: 100 texts -> 1 embedding).
                lambda b=batch: self.client.models.embed_content(
                    model=model, contents=[types.Content(parts=[types.Part(text=t)]) for t in b],
                    config=cfg,
                )
            )
            if len(resp.embeddings) != len(batch):
                raise LLMUnavailable(
                    f"embedding count mismatch: {len(resp.embeddings)} for {len(batch)} texts")
            out.extend(list(e.values) for e in resp.embeddings)
            tokens = int(sum(len(t) for t in batch) / 4)
            usage = Usage(
                model=model, task="embedding", latency_ms=int((time.monotonic() - t0) * 1000),
                prompt_tokens=tokens, cost_usd=tokens * self.s.PRICE_EMBEDDING_PER_M / 1e6,
            )
            self._record(usage, "ok")
        return out

    def _record(self, usage: Usage, status: str) -> None:
        request_context.add_usage(usage)
        metrics.record_llm(usage)
        log.info("llm_call", extra={"fields": {
            "task": usage.task, "model": usage.model, "latency_ms": usage.latency_ms,
            "prompt_tokens": usage.prompt_tokens, "output_tokens": usage.output_tokens,
            "thinking_tokens": usage.thinking_tokens, "cost_usd": usage.cost_usd,
            "status": status,
        }})
