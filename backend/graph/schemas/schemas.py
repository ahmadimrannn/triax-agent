from pydantic import BaseModel, Field
from typing import Literal

class TriageAgentSchema(BaseModel):
    category: Literal["billing", "account", "technical", "integration", "usage", "feature_request", "security", "other"] = Field(description="Category of the ticket text.")
    urgency: Literal["low", "medium", "high", "critical"] = Field(description="Urgency of the ticket text.")
