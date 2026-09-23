from langgraph.graph import StateGraph, START, END

from graph.state.state import AgentState
from graph.nodes.triage_agent_node import triage_agent_node
from tools import db_pool


def build_graph():
    if db_pool.checkpointer is None:
        raise RuntimeError(
            "LangGraph checkpointer has not been initialized."
        )

    builder = StateGraph(AgentState)

    builder.add_node(
        "triage_agent",
        triage_agent_node,
    )

    builder.add_edge(START, "triage_agent")
    builder.add_edge("triage_agent", END)

    return builder.compile(
        checkpointer=db_pool.checkpointer,
    )