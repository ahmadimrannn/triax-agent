from dataclasses import dataclass
from graph.state.state import GateDecision

@dataclass(frozen=True)
class GateConfig:
    auto_send_max_distance: float = 0.50
    never_auto_send_categories: frozenset = frozenset({"billing", "security"})


def _check_issue(key, issue, chunks, draft, config):
    tag = f"issue {key}"
    reasons = []
    score = None

    if issue["category"] in config.never_auto_send_categories:
        reasons.append(f"{tag}: category '{issue['category']}' is always reviewed")

    if draft is None:
        reasons.append(f"{tag}: no draft")
        return reasons, score

    if draft["category"] != issue["category"]:
        reasons.append(f"{tag}: draft category '{draft['category']}' differs from triage category '{issue['category']}'")
    if draft["status"] != "ok":
        reasons.append(f"{tag}: draft status '{draft['status']}'")
    if draft["grounding_status"] != "grounded":
        reasons.append(f"{tag}: grounding '{draft['grounding_status']}'")
    if draft["uncovered_aspects"].strip():
        reasons.append(f"{tag}: has uncovered aspects")
    if not draft["draft_text"].strip():
        reasons.append(f"{tag}: empty draft text")

    cited = draft["citations"]
    if not cited:
        reasons.append(f"{tag}: no citations")

    distance_by_id = {c["chunk_id"]: c["distance"] for c in chunks}
    if not distance_by_id:
        reasons.append(f"{tag}: no retrieved chunks")
    if any(c not in distance_by_id for c in cited):
        reasons.append(f"{tag}: cites a chunk that was not retrieved")

    cited_distances = [distance_by_id[c] for c in cited if c in distance_by_id]
    if cited_distances:
        score = max(cited_distances)
        if score > config.auto_send_max_distance:
            reasons.append(f"{tag}: worst cited distance {score:.4f} is above {config.auto_send_max_distance}")

    return reasons, score


def decide(issues, retrieved_results, draft_results, config=GateConfig()) -> GateDecision:
    reasons = []
    scores = []

    if not issues:
        reasons.append("no issues on the ticket")

    drafts = {d["issue_id"]: d for d in (draft_results or [])}
    expected_keys = {str(i) for i in range(len(issues))}
    extra = set(drafts) - expected_keys
    if extra:
        reasons.append(f"drafts for unknown issues: {sorted(extra)}")

    for idx, issue in enumerate(issues):
        key = str(idx)
        issue_reasons, score = _check_issue(key, issue, retrieved_results.get(key, []), drafts.get(key), config)
        reasons.extend(issue_reasons)
        if score is not None:
            scores.append(score)

    return {
        "route": "human_review" if reasons else "auto_send",
        "reasons": reasons,
        "ticket_score": max(scores) if scores else None,
        "threshold": config.auto_send_max_distance,
    }


def run_gate(issues, retrieved_results, draft_results, config=GateConfig()) -> GateDecision:
    try:
        return decide(issues, retrieved_results, draft_results, config)
    except Exception as e:
        return {
            "route": "human_review",
            "reasons": [f"gate_error: {type(e).__name__}: {e}"],
            "ticket_score": None,
            "threshold": config.auto_send_max_distance,
        }