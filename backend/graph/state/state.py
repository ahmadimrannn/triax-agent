from typing import TypedDict
from uuid import UUID

class TicketIssues(TypedDict):
    category: str
    urgency: str
    summary: str

class RetrievedChunk(TypedDict):
    chunk_id: str
    chunk_text: str
    distance: float

class AgentState(TypedDict):
    tenant_id: UUID
    ticket_text: str

    ticket_id: UUID
    tenant_name: str
    issues: list[TicketIssues]
    
    retrieved_results: dict[str, list[RetrievedChunk]]
    draft_results: list[dict]