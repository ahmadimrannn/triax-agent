from typing import TypedDict
from uuid import UUID

class AgentState(TypedDict):
    tenant_id: UUID
    ticket_text: str

    ticket_id: UUID
    category: str
    urgency: str

    retrieved_results: list
