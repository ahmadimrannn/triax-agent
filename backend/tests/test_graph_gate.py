import asyncio
import importlib
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

NEEDLE = "def " + "build_graph"


def find_builder_module():
    for path in ROOT.rglob("*.py"):
        if ".venv" in path.parts or "__pycache__" in path.parts or path.resolve() == Path(__file__).resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if NEEDLE in text and "StateGraph" in text:
            return ".".join(path.relative_to(ROOT).with_suffix("").parts)
    raise RuntimeError("could not find the file that defines build_graph")


REAL_ID = "704d132c-4570-4e28-97e3-e16bfced0093"


def fake_nodes(distance=0.15, grounding="grounded", category="usage", break_draft=False, uuid_chunk_ids=False):
    good = grounding == "grounded"
    chunk_id = uuid.UUID(REAL_ID) if uuid_chunk_ids else "c1"
    cited = REAL_ID if uuid_chunk_ids else "c1"

    async def triage(state):
        return {
            "ticket_id": "T-1",
            "tenant_name": "Northstar Labs",
            "issues": [{"category": category, "urgency": "low", "summary": "s"}],
        }

    async def retrieval(state):
        return {"retrieved_results": {"0": [{"chunk_id": chunk_id, "chunk_text": "t", "distance": distance}]}}

    async def draft(state):
        item = {
            "issue_id": "0",
            "category": category,
            "status": "ok",
            "grounding_status": grounding,
            "draft_text": "Here is the answer." if good else "",
            "citations": [cited] if good else [],
            "uncovered_aspects": "" if good else "the KB does not cover this",
        }
        if break_draft:
            del item["grounding_status"]
        return {"draft_results": [item]}

    return triage, retrieval, draft


def build_with(fakes):
    from langgraph.checkpoint.memory import MemorySaver
    from tools import db_pool

    module = importlib.import_module(find_builder_module())
    db_pool.checkpointer = MemorySaver()
    module.triage_agent_node, module.retrieval_node, module.draft_agent_node = fakes
    return module.build_graph()


def run_ticket(fakes):
    graph = build_with(fakes)
    initial = {
        "tenant_id": uuid.uuid4(),
        "ticket_text": "test ticket",
        "ticket_id": "",
        "tenant_name": "",
        "issues": [],
        "retrieved_results": {},
        "draft_results": [],
        "gate_decision": {},
    }
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    return asyncio.run(graph.ainvoke(initial, config))


def test_high_confidence_ticket_reaches_auto_send_through_the_real_graph():
    final = run_ticket(fake_nodes(distance=0.15))
    assert final["gate_decision"]["route"] == "auto_send"
    assert "auto_send_reason" in final
    assert "human_review_reason" not in final


def test_low_confidence_ticket_reaches_human_review_through_the_real_graph():
    final = run_ticket(fake_nodes(distance=0.90))
    assert final["gate_decision"]["route"] == "human_review"
    assert "human_review_reason" in final
    assert "auto_send_reason" not in final
    assert "worst cited distance" in final["human_review_reason"]


def test_postgres_style_uuid_chunk_ids_do_not_break_auto_send():
    final = run_ticket(fake_nodes(distance=0.15, uuid_chunk_ids=True))
    assert final["gate_decision"]["route"] == "auto_send", final["gate_decision"]["reasons"]
    assert "auto_send_reason" in final


def test_partial_grounding_reaches_human_review():
    final = run_ticket(fake_nodes(distance=0.15, grounding="partial"))
    assert "human_review_reason" in final
    assert "auto_send_reason" not in final


def test_billing_ticket_reaches_human_review_even_with_perfect_signals():
    final = run_ticket(fake_nodes(distance=0.10, category="billing"))
    assert "human_review_reason" in final
    assert "auto_send_reason" not in final


def test_gate_crash_from_a_malformed_draft_reaches_human_review():
    final = run_ticket(fake_nodes(distance=0.15, break_draft=True))
    assert final["gate_decision"]["route"] == "human_review"
    assert "gate_error" in final["gate_decision"]["reasons"][0]
    assert "auto_send_reason" not in final


def test_only_the_gate_can_lead_to_auto_send_in_the_compiled_graph():
    graph = build_with(fake_nodes())
    edges = graph.get_graph().edges
    into_auto_send = sorted({e.source for e in edges if e.target == "auto_send"})
    into_review = sorted({e.source for e in edges if e.target == "human_review"})
    assert into_auto_send == ["confidence_gate"]
    assert into_review == ["confidence_gate"]


def test_auto_send_node_refuses_to_run_without_a_gate_approval():
    from graph.gate import GateBypassError
    from graph.nodes.auto_send import auto_send_node

    for state in (
        {},
        {"gate_decision": {}},
        {"gate_decision": {"route": "human_review", "reasons": ["x"], "draft_hash": ""}},
    ):
        try:
            asyncio.run(auto_send_node(state))
        except GateBypassError:
            continue
        raise AssertionError(f"auto_send_node ran without approval for state {state}")


def test_auto_send_node_refuses_when_drafts_changed_after_the_gate():
    from graph.gate import GateBypassError, run_gate
    from graph.nodes.auto_send import auto_send_node

    triage, retrieval, draft = fake_nodes(distance=0.15)
    issues = asyncio.run(triage({}))["issues"]
    chunks = asyncio.run(retrieval({}))["retrieved_results"]
    drafts = asyncio.run(draft({}))["draft_results"]
    state = {"issues": issues, "retrieved_results": chunks, "draft_results": drafts}
    state["gate_decision"] = run_gate(issues, chunks, drafts)
    assert asyncio.run(auto_send_node(state))["auto_send_reason"]
    drafts[0]["draft_text"] = "edited after approval"
    try:
        asyncio.run(auto_send_node(state))
    except GateBypassError:
        return
    raise AssertionError("auto_send_node ran on drafts the gate never approved")


if __name__ == "__main__":
    all_tests = [(name, fn) for name, fn in list(globals().items()) if name.startswith("test_") and callable(fn)]
    failures = 0
    for name, fn in all_tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:
            failures += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(all_tests) - failures} passed, {failures} failed")
    sys.exit(1 if failures else 0)