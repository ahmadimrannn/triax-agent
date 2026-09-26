from pydantic import BaseModel, Field
from typing import Literal

class TicketIssue(BaseModel):
    category: Literal["billing", "account", "technical", "integration", "usage", "feature_request", "security", "performance", "other"] = Field(
        description="Category of this specific issue."
    )
    urgency: Literal["low", "medium", "high", "critical"] = Field(
        description="Urgency of this specific issue, judged independently of the other issues in the ticket."
    )
    summary: str = Field(
        description="One sentence describing just this issue, pulled from the ticket text. Used to build a separate retrieval query for this issue."
    )
 
 
class TriageAgentSchema(BaseModel):
    issues: list[TicketIssue] = Field(
        description="One entry per distinct problem in the ticket. Most tickets have exactly one issue. Only split into multiple entries when the ticket describes genuinely separate problems, not just multiple details about the same problem."
    )
