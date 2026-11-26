"""Shared contracts. Every module group builds against these models; change only from the main session."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Agent = Literal["knowledge", "support", "escalation"]
Source = Literal["rag", "web"]
Lang = Literal["en", "pt"]
Role = Literal["merchant", "operator"]
PlannedRefusal = Literal["unsafe", "out_of_scope", "other_merchant", "prompt_injection"]
RefusalReason = Literal[
    "sensitive_data", "other_merchant", "prompt_injection", "unsafe", "out_of_scope", "too_long"
]
EscalationReason = Literal[
    "human_requested", "no_grounding", "tool_failure", "llm_failure", "budget_exceeded"
]
ChatStatus = Literal["answered", "awaiting_human", "refused"]
ObservationStatus = Literal["answered", "partial", "no_grounding", "failed"]
TicketStatus = Literal["open", "claimed", "resolved", "rejected"]


class Principal(BaseModel):
    sub: str
    role: Role


class Step(BaseModel):
    id: str = Field(description="short id such as s1, s2")
    agent: Agent
    source: Source | None = Field(default=None, description="only for knowledge: rag or web")
    query: str = Field(description="self-contained query for this step, in the user's language")


class Plan(BaseModel):
    steps: list[Step] = Field(default_factory=list)
    lang: Lang = "en"
    standalone: str = Field(description="the user message rewritten to stand alone, resolving references to earlier turns")
    parts: list[str] = Field(default_factory=list, description="each distinct question or request in the message")
    refusal_reason: PlannedRefusal | None = None
    escalate_reason: Literal["human_requested"] | None = None


class PlanRevision(BaseModel):
    iteration: int
    action: Literal["add", "retry", "drop"]
    step_id: str
    reason: str


class Evidence(BaseModel):
    url: str
    title: str = ""
    score: float = 0.0
    excerpt: str = ""


class Usage(BaseModel):
    model: str = ""
    task: str = ""
    latency_ms: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    search_queries: int = 0
    cost_usd: float = 0.0


class Observation(BaseModel):
    step_id: str
    agent: Agent
    source: Source | None = None
    status: ObservationStatus
    answer: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    unanswered: list[str] = Field(default_factory=list)
    data: dict[str, Any] | None = None
    usage: list[Usage] = Field(default_factory=list)
    error: str | None = None


class CriticVerdict(BaseModel):
    complete: bool
    missing_parts: list[str] = Field(default_factory=list)
    revisions: list[PlanRevision] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    """Structured output of an answering agent."""
    answer: str
    grounded: bool = Field(description="true only if the answer is fully supported by the provided context")
    cited_ids: list[str] = Field(default_factory=list, description="ids of the context items used")
    unanswered: list[str] = Field(default_factory=list, description="parts the context could not answer")


class TraceTotal(BaseModel):
    tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class Trace(BaseModel):
    plan_revisions: list[PlanRevision] = Field(default_factory=list)
    critic_notes: list[str] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    steps_usage: list[Usage] = Field(default_factory=list)
    total: TraceTotal = Field(default_factory=TraceTotal)


class SourceRef(BaseModel):
    title: str = ""
    url: str


class ChatRequest(BaseModel):
    message: str
    user_id: str
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    status: ChatStatus
    refusal_reason: RefusalReason | None = None
    route: str
    sources: list[SourceRef] = Field(default_factory=list)
    ticket_id: str | None = None
    conversation_id: str
    request_id: str
    trace: Trace = Field(default_factory=Trace)


class Refusal(BaseModel):
    reason: RefusalReason
    message: str
    lang: Lang = "en"


class Ticket(BaseModel):
    id: str
    conversation_id: str
    owner_sub: str
    reason: str
    status: TicketStatus
    claimed_by: str | None = None
    created_at: datetime
    updated_at: datetime
    resolution: dict[str, Any] | None = None


class RankedChunk(BaseModel):
    id: str
    url: str
    title: str = ""
    heading: str = ""
    text: str
    site: Literal["br", "global"] = "br"
    kind: str = "section"
    is_rule: bool = False
    similarity: float = 0.0
    score: float = 0.0
