from langgraph.graph import StateGraph, START, END

from graph.state.state import AgentState
from graph.nodes.triage_agent_node import triage_agent_node
from graph.nodes.retrieval_node import retrieval_node
from graph.nodes.draft_agent_node import draft_agent_node
from graph.nodes.confidence_gate_node import confidence_gate_node
from graph.nodes.auto_send import auto_send_node
from graph.nodes.human_review import human_review_node

from graph.router.router import route_after_gate
from tools import db_pool


def build_graph():
    if db_pool.checkpointer is None:
        raise RuntimeError(
            "LangGraph checkpointer has not been initialized."
        )

    builder = StateGraph(AgentState)

    builder.add_node("triage_agent", triage_agent_node)
    builder.add_node("retrieval_node", retrieval_node)
    builder.add_node("draft_agent", draft_agent_node)
    builder.add_node("confidence_gate", confidence_gate_node)
    builder.add_node("auto_send", auto_send_node)
    builder.add_node("human_review", human_review_node)

    builder.add_edge(START, "triage_agent")
    builder.add_edge("triage_agent", "retrieval_node")
    builder.add_edge("retrieval_node", "draft_agent")
    builder.add_edge("draft_agent", "confidence_gate")
    builder.add_conditional_edges(
        "confidence_gate",
        route_after_gate,
        {
            "auto_send": "auto_send",
            "human_review": "human_review"
        }
    )
    builder.add_edge("auto_send", END) 
    builder.add_edge("human_review", END)

    return builder.compile(
        checkpointer=db_pool.checkpointer,
    )