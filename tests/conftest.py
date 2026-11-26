"""Shared fixtures: test settings with a temp data dir and a scripted FakeLLM (no network)."""

import shutil
from pathlib import Path

import pytest
from pydantic import BaseModel

from getnet_multi_agent.contracts import Usage
from getnet_multi_agent.core.llm import LLMResult, hash_embedding
from getnet_multi_agent.core.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


class FakeLLM:
    """responses: task -> LLMResult | BaseModel | dict | str | Exception | list of those | callable.

    A list is consumed in order (the last item repeats). A callable receives the call kwargs.
    """

    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.calls: list[dict] = []
        self.embed_calls = 0

    def generate(self, task, contents, *, schema=None, tools=None, search=False, system=None):
        if search and tools:
            raise ValueError("search and tools cannot share a request")
        call = dict(task=task, contents=contents, schema=schema, tools=tools, search=search, system=system)
        self.calls.append(call)
        r = self.responses.get(task)
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else (r[0] if r else None)
        if callable(r) and not isinstance(r, type):
            r = r(**call)
        if r is None:
            raise AssertionError(f"FakeLLM: no scripted response for task {task!r}")
        if isinstance(r, Exception):
            raise r
        usage = Usage(model=f"fake-{task}", task=task, prompt_tokens=10, output_tokens=5)
        if isinstance(r, LLMResult):
            if not r.usage.model:
                r.usage = usage
            return r
        if isinstance(r, BaseModel):
            return LLMResult(text=r.model_dump_json(), parsed=r, usage=usage)
        if isinstance(r, dict) and schema is not None:
            parsed = schema.model_validate(r)
            return LLMResult(text=parsed.model_dump_json(), parsed=parsed, usage=usage)
        return LLMResult(text=str(r), usage=usage)

    def embed(self, texts, task_type):
        self.embed_calls += 1
        return [hash_embedding(t) for t in texts]

    def tasks(self):
        return [c["task"] for c in self.calls]


@pytest.fixture
def settings(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(ROOT / "data" / "merchants.json", data / "merchants.json") if (
        ROOT / "data" / "merchants.json"
    ).exists() else None
    return Settings(
        _env_file=None,
        DATA_DIR=str(data),
        LLM_MODE="stub",
        JWT_SECRET="test-jwt-secret-with-enough-length-0123456789",
        PSEUDONYM_KEY="test-pseudonym-key",
        GEMINI_API_KEY="",
    )


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def crawl_cache_dir():
    return ROOT / "data" / "crawl_cache"
