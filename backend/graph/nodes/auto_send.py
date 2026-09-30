from graph.gate import verify_approval
from graph.state.state import AgentState


async def auto_send_node(state: AgentState):
    verify_approval(state)

    return {
        "auto_send_reason": "Auto sending the ticket. Because the decision is auto_send"
    }