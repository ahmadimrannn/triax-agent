import hashlib
import json
from dataclasses import dataclass
from typing import Literal, TypedDict


@dataclass(frozen=True)
class GateConfig:
    auto_send_max_distance: float = 0.50
    never_auto_send_categories: frozenset = frozenset({"billing", "security"})


class GateDecision(TypedDict):
    route: Literal["auto_send", "human_review"]
    reasons: list[str]
    ticket_score: float | None
    threshold: float
    draft_hash: str


class GateBypassError(Exception):
    pass


def draft_fingerprint(draft_results):
    parts = sorted((str(d["issue_id"]), d["draft_text"]) for d in (draft_results or []))
    return hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()


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
        "draft_hash": draft_fingerprint(draft_results),
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
            "draft_hash": "",
        }


def gate_node(state):
    decision = run_gate(
        state.get("issues") or [],
        state.get("retrieved_results") or {},
        state.get("draft_results"),
    )
    return {"gate_decision": decision}


def route_after_gate(state):
    decision = state.get("gate_decision")
    if isinstance(decision, dict) and decision.get("route") == "auto_send":
        return "auto_send"
    return "human_review"


def verify_approval(state):
    decision = state.get("gate_decision")
    if not isinstance(decision, dict) or decision.get("route") != "auto_send":
        raise GateBypassError("auto_send was reached without an auto_send decision from the gate")
    if decision.get("reasons"):
        raise GateBypassError("gate decision says auto_send but still lists review reasons")
    try:
        current_hash = draft_fingerprint(state.get("draft_results"))
    except Exception as e:
        raise GateBypassError(f"could not fingerprint the drafts: {e!r}") from e
    if decision.get("draft_hash") != current_hash:
        raise GateBypassError("the drafts changed after the gate approved them")
    return decision