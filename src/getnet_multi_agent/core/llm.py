"""LLM wrapper interface. All model calls go through an LLMClient (GeminiClient live, StubClient, fakes)."""

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from getnet_multi_agent.contracts import Usage

Task = Literal[
    "router", "critic", "summary", "personality", "knowledge", "support", "synthesis", "judge"
]
EmbedTaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
EMBED_DIM = 768


class LLMUnavailable(RuntimeError):
    """The model stayed unavailable after the retry, timed out or returned an unusable answer."""


class BudgetExceeded(RuntimeError):
    """The per-request token budget is spent."""


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema (type=object)


class FunctionCall(BaseModel):
    name: str
    args: dict[str, Any] = {}


class GroundingSource(BaseModel):
    title: str = ""
    uri: str


class Message(BaseModel):
    """Provider-neutral conversation item for multi-turn and tool loops."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    role: Literal["user", "model", "tool"]
    text: str = ""
    raw: Any = None  # provider content of a model turn, sent back whole (thought signatures)
    tool_name: str | None = None
    tool_response: dict[str, Any] | None = None


@dataclass
class LLMResult:
    text: str = ""
    parsed: Any = None
    content: Any = None
    function_calls: list[FunctionCall] = field(default_factory=list)
    grounding: list[GroundingSource] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)

    def as_message(self) -> Message:
        return Message(role="model", text=self.text, raw=self.content)


class LLMClient(Protocol):
    def generate(
        self,
        task: Task,
        contents: str | list[Message],
        *,
        schema: type[BaseModel] | None = None,
        tools: list[ToolSpec] | None = None,
        search: bool = False,
        system: str | None = None,
    ) -> LLMResult: ...

    def embed(self, texts: list[str], task_type: EmbedTaskType) -> list[list[float]]: ...


_WORD = re.compile(r"\w+", re.UNICODE)


def hash_embedding(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Deterministic bag-of-words hash embedding (stub mode and tests). Similar words → similar vectors."""
    vec = [0.0] * dim
    for tok in _WORD.findall(text.lower()):
        h = hashlib.sha256(tok.encode()).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        vec[idx] += 1.0 if h[4] % 2 == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def get_llm(settings) -> LLMClient:
    if settings.LLM_MODE == "stub":
        from getnet_multi_agent.core.stub_client import StubClient

        return StubClient(settings)
    from getnet_multi_agent.core.gemini_client import GeminiClient

    return GeminiClient(settings)
