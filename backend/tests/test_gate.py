from graph import gate

GateConfig = gate.GateConfig
GateBypassError = gate.GateBypassError
decide = gate.decide
draft_fingerprint = gate.draft_fingerprint
gate_node = gate.gate_node
route_after_gate = gate.route_after_gate
run_gate = gate.run_gate
verify_approval = gate.verify_approval


def chunk(chunk_id, distance):
    return {"chunk_id": chunk_id, "chunk_text": "text", "distance": distance}


def issue(category="usage"):
    return {"category": category, "urgency": "low", "summary": "s"}


def draft(issue_id="0", category="usage", grounding="grounded", text="Here is the answer.", cites=("c1",), uncovered="", status="ok"):
    return {
        "issue_id": issue_id, "category": category, "status": status,
        "grounding_status": grounding, "draft_text": text,
        "citations": list(cites), "uncovered_aspects": uncovered,
    }


def good_ticket(distance=0.15):
    return [issue()], {"0": [chunk("c1", distance), chunk("c2", 0.30)]}, [draft()]


def test_high_confidence_draft_is_auto_sent():
    issues, chunks, drafts = good_ticket(distance=0.15)
    result = run_gate(issues, chunks, drafts)
    assert result["route"] == "auto_send"
    assert result["reasons"] == []
    assert result["ticket_score"] == 0.15


def test_low_confidence_draft_goes_to_review():
    issues, chunks, drafts = good_ticket(distance=0.90)
    result = run_gate(issues, chunks, drafts)
    assert result["route"] == "human_review"
    assert any("worst cited distance" in r for r in result["reasons"])


def test_threshold_boundary_is_pinned():
    config = GateConfig(auto_send_max_distance=0.50)
    issues, chunks, drafts = good_ticket(distance=0.50)
    assert run_gate(issues, chunks, drafts, config)["route"] == "auto_send"
    issues, chunks, drafts = good_ticket(distance=0.5001)
    assert run_gate(issues, chunks, drafts, config)["route"] == "human_review"


def test_worst_cited_chunk_counts_not_the_best():
    issues = [issue()]
    chunks = {"0": [chunk("c1", 0.10), chunk("c2", 0.70)]}
    drafts = [draft(cites=("c1", "c2"))]
    assert run_gate(issues, chunks, drafts)["route"] == "human_review"


def test_partial_and_insufficient_grounding_go_to_review():
    issues, chunks, _ = good_ticket()
    assert run_gate(issues, chunks, [draft(grounding="partial")])["route"] == "human_review"
    blank = draft(grounding="insufficient_evidence", text="", cites=())
    assert run_gate(issues, chunks, [blank])["route"] == "human_review"


def test_uncovered_aspects_go_to_review():
    issues, chunks, _ = good_ticket()
    assert run_gate(issues, chunks, [draft(uncovered="does not cover timeouts")])["route"] == "human_review"


def test_no_citations_goes_to_review():
    issues, chunks, _ = good_ticket()
    assert run_gate(issues, chunks, [draft(cites=())])["route"] == "human_review"


def test_citation_to_a_chunk_that_was_not_retrieved_goes_to_review():
    issues, chunks, _ = good_ticket()
    assert run_gate(issues, chunks, [draft(cites=("made-up-id",))])["route"] == "human_review"


def test_bad_draft_status_goes_to_review():
    issues, chunks, _ = good_ticket()
    assert run_gate(issues, chunks, [draft(status="failed")])["route"] == "human_review"


def test_billing_and_security_are_always_reviewed_even_with_perfect_signals():
    for category in ("billing", "security"):
        result = run_gate([issue(category)], {"0": [chunk("c1", 0.10)]}, [draft(category=category)])
        assert result["route"] == "human_review"
        assert any("always reviewed" in r for r in result["reasons"])


def test_category_mismatch_between_triage_and_draft_goes_to_review():
    issues, chunks, _ = good_ticket()
    assert run_gate(issues, chunks, [draft(category="account")])["route"] == "human_review"


def test_two_issues_one_weak_sends_the_whole_ticket_to_review():
    issues = [issue(), issue()]
    chunks = {"0": [chunk("c1", 0.10)], "1": []}
    drafts = [draft("0"), draft("1", grounding="insufficient_evidence", text="", cites=())]
    result = run_gate(issues, chunks, drafts)
    assert result["route"] == "human_review"
    assert all(r.startswith("issue 1") for r in result["reasons"])


def test_issue_missing_from_retrieved_results_is_not_skipped():
    issues = [issue(), issue()]
    chunks = {"0": [chunk("c1", 0.10)]}
    drafts = [draft("0"), draft("1")]
    assert run_gate(issues, chunks, drafts)["route"] == "human_review"


def test_issue_missing_a_draft_is_not_skipped():
    issues = [issue(), issue()]
    chunks = {"0": [chunk("c1", 0.10)], "1": [chunk("c1", 0.10)]}
    assert run_gate(issues, chunks, [draft("0")])["route"] == "human_review"


def test_draft_for_an_unknown_issue_goes_to_review():
    issues, chunks, _ = good_ticket()
    assert run_gate(issues, chunks, [draft("0"), draft("5")])["route"] == "human_review"


def test_no_drafts_at_all_goes_to_review():
    issues, chunks, _ = good_ticket()
    assert run_gate(issues, chunks, None)["route"] == "human_review"
    assert run_gate(issues, chunks, [])["route"] == "human_review"


def test_no_issues_goes_to_review():
    assert run_gate([], {}, [])["route"] == "human_review"


def test_gate_crash_on_malformed_draft_fails_closed():
    issues, chunks, _ = good_ticket()
    broken = draft()
    del broken["grounding_status"]
    result = run_gate(issues, chunks, [broken])
    assert result["route"] == "human_review"
    assert result["reasons"][0].startswith("gate_error")


def test_gate_crash_inside_decide_fails_closed():
    def boom(*args, **kwargs):
        raise RuntimeError("forced failure")
    original = gate.decide
    gate.decide = boom
    try:
        issues, chunks, drafts = good_ticket()
        result = run_gate(issues, chunks, drafts)
    finally:
        gate.decide = original
    assert result["route"] == "human_review"
    assert "forced failure" in result["reasons"][0]


def test_router_defaults_to_review():
    assert route_after_gate({}) == "human_review"
    assert route_after_gate({"gate_decision": None}) == "human_review"
    assert route_after_gate({"gate_decision": {"route": "something_else"}}) == "human_review"
    assert route_after_gate({"gate_decision": "auto_send"}) == "human_review"
    assert route_after_gate({"gate_decision": {"route": "auto_send"}}) == "auto_send"


def test_gate_node_and_router_together():
    issues, chunks, drafts = good_ticket(distance=0.15)
    good_state = {"issues": issues, "retrieved_results": chunks, "draft_results": drafts}
    assert route_after_gate({**good_state, **gate_node(good_state)}) == "auto_send"

    issues, chunks, drafts = good_ticket(distance=0.90)
    bad_state = {"issues": issues, "retrieved_results": chunks, "draft_results": drafts}
    assert route_after_gate({**bad_state, **gate_node(bad_state)}) == "human_review"

    assert route_after_gate({**{}, **gate_node({})}) == "human_review"


def test_real_a1_draft_shape_goes_to_review():
    issues = [{"category": "integration", "urgency": "high", "summary": "webhooks stopped"}]
    chunks = {"0": [chunk("704d132c-4570-4e28-97e3-e16bfced0093", 0.30)]}
    drafts = [{
        "issue_id": "0", "category": "integration", "status": "ok", "grounding_status": "partial",
        "draft_text": "We are investigating your webhook issue.",
        "citations": ["704d132c-4570-4e28-97e3-e16bfced0093"],
        "uncovered_aspects": "The retrieved chunks do not explain why the webhooks stopped.",
    }]
    result = run_gate(issues, chunks, drafts)
    assert result["route"] == "human_review"
    assert any("grounding 'partial'" in r for r in result["reasons"])


def test_real_a7_draft_shape_is_held_only_because_security_is_always_reviewed():
    ids = ["2fc6f692-fdaf-4db6-abe7-eec0de70a7fe", "218041b7-110d-47c7-8225-732efe8d487f", "4c80cd45-778d-4100-9632-123ae70b94ad"]
    chunks = {"0": [chunk(ids[0], 0.41), chunk(ids[1], 0.45), chunk(ids[2], 0.47)]}
    drafts = [{
        "issue_id": "0", "category": "security", "status": "ok", "grounding_status": "grounded",
        "draft_text": "We are treating your report as security-sensitive.",
        "citations": ids, "uncovered_aspects": "",
    }]
    held = run_gate([{"category": "security", "urgency": "high", "summary": "s"}], chunks, drafts)
    assert held["route"] == "human_review"
    assert held["reasons"] == ["issue 0: category 'security' is always reviewed"]

    no_rule = GateConfig(never_auto_send_categories=frozenset())
    sent = run_gate([{"category": "security", "urgency": "high", "summary": "s"}], chunks, drafts, no_rule)
    assert sent["route"] == "auto_send"


def approved_state(distance=0.15):
    issues, chunks, drafts = good_ticket(distance)
    state = {"issues": issues, "retrieved_results": chunks, "draft_results": drafts}
    state["gate_decision"] = run_gate(issues, chunks, drafts)
    return state


def raises_bypass(state):
    try:
        verify_approval(state)
    except GateBypassError:
        return True
    return False


def test_decision_carries_a_fingerprint_of_the_drafts():
    state = approved_state()
    assert state["gate_decision"]["draft_hash"] == draft_fingerprint(state["draft_results"])
    assert len(state["gate_decision"]["draft_hash"]) == 64


def test_fingerprint_changes_with_text_and_ignores_order():
    a = [draft("0", text="one"), draft("1", text="two")]
    b = [draft("1", text="two"), draft("0", text="one")]
    c = [draft("0", text="one"), draft("1", text="two changed")]
    assert draft_fingerprint(a) == draft_fingerprint(b)
    assert draft_fingerprint(a) != draft_fingerprint(c)


def test_verify_approval_accepts_a_real_gate_approval():
    state = approved_state()
    assert verify_approval(state)["route"] == "auto_send"


def test_verify_approval_refuses_review_decision_missing_decision_and_junk():
    state = approved_state(distance=0.90)
    assert state["gate_decision"]["route"] == "human_review"
    assert raises_bypass(state)
    assert raises_bypass({"draft_results": []})
    assert raises_bypass({"gate_decision": {}, "draft_results": []})
    assert raises_bypass({"gate_decision": "auto_send", "draft_results": []})


def test_verify_approval_refuses_when_drafts_changed_after_the_gate():
    state = approved_state()
    state["draft_results"][0]["draft_text"] = "Something the gate never saw."
    assert raises_bypass(state)


def test_verify_approval_refuses_a_hand_made_auto_send_decision():
    state = approved_state()
    forged = {"route": "auto_send", "reasons": [], "draft_hash": "not-the-real-hash"}
    assert raises_bypass({**state, "gate_decision": forged})
    with_reasons = {**state["gate_decision"], "reasons": ["issue 0: grounding 'partial'"]}
    assert raises_bypass({**state, "gate_decision": with_reasons})


def show(title, issues, chunks, drafts):
    result = run_gate(issues, chunks, drafts)
    print(f"\n{title}")
    print(f"  route        : {result['route']}")
    print(f"  ticket_score : {result['ticket_score']}")
    print(f"  reasons      : {result['reasons'] if result['reasons'] else 'none'}")


def demo():
    print("\n" + "=" * 60)
    print("PROOF FOR THE DEFINITION OF DONE (forced inputs, no LLM)")
    print("=" * 60)
    issues, chunks, drafts = good_ticket(distance=0.15)
    show("HIGH confidence: grounded draft, cited chunk at distance 0.15", issues, chunks, drafts)
    issues, chunks, drafts = good_ticket(distance=0.90)
    show("LOW confidence: same draft, cited chunk at distance 0.90", issues, chunks, drafts)
    issues, chunks, _ = good_ticket(distance=0.15)
    show("LOW confidence: distance is fine but draft is only 'partial'", issues, chunks, [draft(grounding="partial")])
    broken = draft()
    del broken["grounding_status"]
    show("GATE CRASH: draft is missing a field", issues, chunks, [broken])


if __name__ == "__main__":
    import sys

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
    demo()
    sys.exit(1 if failures else 0)