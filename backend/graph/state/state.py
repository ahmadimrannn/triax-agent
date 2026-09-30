from typing import TypedDict, Literal
from uuid import UUID

class TicketIssues(TypedDict):
    category: str
    urgency: str
    summary: str

class RetrievedChunk(TypedDict):
    chunk_id: str
    chunk_text: str
    distance: float

class GateDecision(TypedDict):
    route: Literal["auto_send", "human_review"]
    reasons: list[str]
    ticket_score: float | None
    threshold: float

class AgentState(TypedDict):
    tenant_id: UUID
    ticket_text: str

    ticket_id: UUID
    tenant_name: str
    issues: list[TicketIssues]
    
    retrieved_results: dict[str, list[RetrievedChunk]]
    draft_results: list[dict]

    gate_decision: dict[GateDecision]

    auto_send_reason: str
    human_review_reason: str