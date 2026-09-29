from graph.state.state import AgentState

def route_after_gate(state: AgentState):
    decision = state.get("gate_decision")
    if isinstance(decision, dict) and decision.get("route") == "auto_send":
        return "auto_send"
    return "human_review"