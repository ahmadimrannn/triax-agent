import asyncio
import re
import sys
from collections import Counter

import httpx
import os
from dotenv import load_dotenv

load_dotenv()

tenant_id = os.getenv("TENANT_ID")

URL = "http://localhost:8000/tickets/process"
TENANT_ID = tenant_id
RUNS = 2
MAX_AT_ONCE = 7
TIMEOUT = 300

TICKETS = [
    ("A1", "answerable", "hey my webhooks stopped firing since yesterday, nothing hits our endpoint anymore and we are losing events"),
    ("A2", "answerable", "i got charged twice this month for the same thing?? please fix asap"),
    ("A3", "answerable", "getting 429 errors on and off, is there some limit im hitting or what"),
    ("A4", "answerable", "why does my dashboard say ive used 80 percent of my plan when i barely call the api"),
    ("A5", "answerable", "cant log in. it says invalid credentials but i literally just reset my password"),
    ("A6", "uncovered", "api is super slow today, requests take like 10 seconds"),
    ("A7", "answerable", "someone we dont know logged into our account last night, we are worried"),
    ("A8", "answerable", "the signature check on your webhook payloads keeps failing on our side"),
    ("A9", "answerable", "theres a charge on my card i dont recognize from you guys"),
    ("A10", "uncovered", "our integration keeps timing out when it calls your api, it was fine last week"),
    ("U1", "uncovered", "do you have an on-premise version we can host on our own servers"),
    ("U2", "uncovered", "can i pay with crypto instead of a card"),
    ("U3", "uncovered", "whats your ceos email, i have a partnership proposal"),
    ("U4", "uncovered", "can you recommend a good pizza place near your office"),
    ("U5", "uncovered", "this is ridiculous, nothing works, fix it now"),
    ("U6", "uncovered", "can you reissue all of last years invoices with our new company name and tax id"),
    ("U7", "uncovered", "do you guarantee 99.99 percent uptime and give service credits if you miss it"),
    ("U8", "uncovered", "i need your SOC 2 report and data retention policy for our legal team"),
    ("U9", "uncovered", "how do i migrate my whole account and history over from your competitor"),
    ("U10", "multi", "i want my per-minute limit raised to 5000, what does the enterprise plan cost"),
    ("M1", "multi", "our webhooks have been failing since yesterday, and also do you give a discount for paying annually"),
    ("M2", "multi", "i got double charged this month, and separately is there an iOS app to watch my usage"),
]

MUST_NEVER_AUTO_SEND = {"uncovered", "multi"}


def failed(ticket_id, label, message):
    return {"ticket": ticket_id, "label": label, "route": "FAILED", "reasons": [], "score": None,
            "error": message, "mismatch": False, "drafts": [], "retrieved": {}}


async def run_one(client, gate, ticket):
    ticket_id, label, text = ticket
    async with gate:
        try:
            resp = await client.post(URL, json={"tenant_id": TENANT_ID, "ticket_text": text})
        except Exception as e:
            return failed(ticket_id, label, f"{type(e).__name__}: {e!r}")
    if resp.status_code != 200:
        return failed(ticket_id, label, f"HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
        decision = data["gate_decision"]
        route = decision["route"]
        ran_auto_send = "auto_send_reason" in data
        ran_review = "human_review_reason" in data
        mismatch = not ((route == "auto_send" and ran_auto_send and not ran_review) or
                        (route == "human_review" and ran_review and not ran_auto_send))
        return {"ticket": ticket_id, "label": label, "route": route, "reasons": decision["reasons"],
                "score": decision.get("ticket_score"), "error": "", "mismatch": mismatch,
                "drafts": data.get("draft_results") or [], "retrieved": data.get("retrieved_results") or {}}
    except Exception as e:
        return failed(ticket_id, label, f"bad response shape ({type(e).__name__}: {e})")


def short(route):
    return {"auto_send": "AUTO", "human_review": "REVIEW", "FAILED": "FAILED"}[route]


def normalise(reason):
    reason = re.sub(r"^issue \d+: ", "", reason)
    return re.sub(r"\d+\.\d+", "X", reason)


def print_draft_health(all_runs):
    total = 0
    blanked = 0
    for run in all_runs:
        for r in run:
            for d in r["drafts"]:
                total += 1
                note = d.get("uncovered_aspects") or ""
                if "did not exactly match" in note or "failed validation" in note or "no valid citations" in note:
                    blanked += 1
    empty = sum(1 for run in all_runs for r in run for d in r["drafts"] if not (d.get("draft_text") or "").strip())
    print("\n" + "=" * 70)
    print("DRAFT HEALTH")
    print("=" * 70)
    print(f"Issue drafts in total: {total}")
    print(f"Drafts with empty text: {empty}")
    print(f"Drafts blanked by the drafter's own citation validation: {blanked}")


def print_empty_answerable_drafts(all_runs):
    print("\n" + "=" * 70)
    print("EMPTY DRAFTS ON ANSWERABLE TICKETS (run 1): what the drafter said was missing")
    print("=" * 70)
    shown = 0
    for r in all_runs[0]:
        if r["label"] != "answerable":
            continue
        for d in r["drafts"]:
            if (d.get("draft_text") or "").strip():
                continue
            print(f"{r['ticket']} issue {d.get('issue_id')} [{d.get('grounding_status')}]: {(d.get('uncovered_aspects') or '')[:300]}")
            shown += 1
    if shown == 0:
        print("None.")


def print_failures(all_runs):
    failed_rows = [r for run in all_runs for r in run if r["route"] == "FAILED"]
    if not failed_rows:
        return
    print("\n" + "=" * 70)
    print("FAILED REQUESTS (look for these timestamps in the server log)")
    print("=" * 70)
    for r in failed_rows:
        print(f"{r['ticket']}: {r['error'][:160]}")


def print_citation_detail(all_runs):
    print("\n" + "=" * 70)
    print("CITATION MISMATCH DETAIL (run 1 only)")
    print("=" * 70)
    shown = 0
    for r in all_runs[0]:
        if not any("not retrieved" in reason for reason in r["reasons"]):
            continue
        print(f"{r['ticket']}:")
        all_ids = {c["chunk_id"] for chunks in r["retrieved"].values() for c in chunks}
        for d in r["drafts"]:
            key = str(d["issue_id"])
            here = {c["chunk_id"] for c in r["retrieved"].get(key, [])}
            for cited in d.get("citations", []):
                if cited in here:
                    verdict = "ok, in this issue's retrieved list"
                elif cited in all_ids:
                    others = [k for k, chunks in r["retrieved"].items() if k != key and cited in {c["chunk_id"] for c in chunks}]
                    verdict = f"real chunk, but only in the retrieved list of issue {others}"
                else:
                    near = [x for x in all_ids if x[:8] == cited[:8]]
                    verdict = f"looks like a corrupted copy of {near[0]}" if near else "matches no retrieved chunk at all"
                print(f"  issue {key}: cited {cited}  ->  {verdict}")
        shown += 1
    if shown == 0:
        print("No ticket had a citation that was missing from the retrieved lists in run 1.")


async def main():
    gate = asyncio.Semaphore(MAX_AT_ONCE)
    all_runs = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for _ in range(RUNS):
            all_runs.append(await asyncio.gather(*[run_one(client, gate, t) for t in TICKETS]))

    by_ticket = {}
    for run in all_runs:
        for r in run:
            by_ticket.setdefault(r["ticket"], []).append(r)

    print(f"{'TICKET':<7}{'LABEL':<12}" + "".join(f"{'RUN' + str(i + 1):<9}" for i in range(RUNS)) + "FIRST REASON (run 1)")
    for tid, rs in by_ticket.items():
        first = rs[0]["reasons"][0] if rs[0]["reasons"] else rs[0]["error"][:80]
        print(f"{tid:<7}{rs[0]['label']:<12}" + "".join(f"{short(r['route']):<9}" for r in rs) + first[:90])

    print("\n" + "=" * 70)
    print("SAFETY CHECKS")
    print("=" * 70)

    bad = sorted({r["ticket"] for run in all_runs for r in run
                  if r["label"] in MUST_NEVER_AUTO_SEND and r["route"] == "auto_send"})
    print(f"Uncovered or multi-issue tickets that were auto-sent (must be empty): {bad}")

    mismatched = sorted({r["ticket"] for run in all_runs for r in run if r["mismatch"]})
    print(f"Tickets where the node that ran did not match the gate decision (must be empty): {mismatched}")

    flaky = sorted(tid for tid, rs in by_ticket.items() if len({r["route"] for r in rs}) > 1)
    print(f"Tickets whose route changed between runs: {flaky}")

    fails = sorted({r["ticket"] for run in all_runs for r in run if r["route"] == "FAILED"})
    print(f"Tickets that failed (HTTP error): {fails}")

    print("\n" + "=" * 70)
    print("RATES")
    print("=" * 70)
    for label in ("answerable", "uncovered", "multi"):
        rows = [r for run in all_runs for r in run if r["label"] == label and r["route"] != "FAILED"]
        auto = sum(1 for r in rows if r["route"] == "auto_send")
        print(f"{label:<11} auto-sent {auto} of {len(rows)} decisions")

    print("\nWhy tickets were held (all runs, most common first):")
    counts = Counter(normalise(reason) for run in all_runs for r in run for reason in r["reasons"])
    for reason, n in counts.most_common(12):
        print(f"  {n:>3}  {reason}")

    print_draft_health(all_runs)
    print_failures(all_runs)
    print_empty_answerable_drafts(all_runs)
    print_citation_detail(all_runs)

    sys.exit(1 if bad or mismatched else 0)


if __name__ == "__main__":
    asyncio.run(main())