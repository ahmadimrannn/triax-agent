from graph.state.state import AgentState
from utils.confidence_gate.gate import run_gate

def confidence_gate_node(state: AgentState):

    decision = run_gate(
        state.get("issues", []),
        state.get("retrieved_results") or {},
        state.get("draft_results"),
    )

    return {"gate_decision": decision}