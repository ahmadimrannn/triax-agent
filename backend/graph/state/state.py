from typing import TypedDict
from uuid import UUID

class TicketIssues(TypedDict):
    category: str
    urgency: str
    summary: str

class AgentState(TypedDict):
    tenant_id: UUID
    ticket_text: str

    ticket_id: UUID

    issues: list[TicketIssues]

    retrieved_results: list
