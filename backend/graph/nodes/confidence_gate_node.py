from graph.gate import gate_node
from graph.state.state import AgentState


async def confidence_gate_node(state: AgentState):
    return gate_node(state)