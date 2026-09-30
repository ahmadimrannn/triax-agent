from graph.state.state import AgentState

async def human_review_node(state: AgentState):
    decision = state.get("gate_decision") or {}
    reasons = decision.get("reasons") or ["no gate decision was recorded"]

    return {
        "human_review_reason": "Waiting for human review: " + "; ".join(reasons)
    }