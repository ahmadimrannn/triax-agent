from typing import TypedDict, Annotated, Literal
import operator

class AgentState(TypedDict):
    tenant_id: str
    ticket_text: str

    ticket_id: str
    category: str
    urgency: str
