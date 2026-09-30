import asyncio
import httpx
import uuid


QUERIES = [
    (
        "1_original_ticket",
        """Hi, I'm the admin for our Northstar Labs workspace and we're having a few issues.

Our API started returning 429 errors today even though the dashboard shows that we've only used around 32,000 units this month. We're on the Growth plan, so I thought we were still well below our 50,000 monthly allowance.""",
        "Should surface the specific edge case: monthly units and per-minute limits are different controls, not just the generic 429 table row.",
    ),
    (
        "2_paraphrase_no_keywords",
        "My API keeps getting rate limited even though I haven't hit my usage cap for the month",
        "Same meaning as query 1, no shared words. Should retrieve the same chunk(s) if embeddings are doing real semantic matching.",
    ),
    (
        "3_refund_after_cancel",
        "I cancelled my subscription today, why wasn't I refunded",
        "Should hit refund policy, the approved answer example, and the cancellation edge case. Check if all three come through or just one.",
    ),
    (
        "4_login_ambiguous_sso",
        "I can't log in, it keeps saying my password reset link is invalid",
        "Ambiguous between SSO and non-SSO accounts. Check whether both branches surface or only one.",
    ),
    (
        "5_security_sensitive",
        "I think someone got into my account without my permission",
        "Should hit the suspicious activity section and example. Check the returned chunk text doesn't leak the internal fraud-threshold line.",
    ),
    (
        "6_known_issue_csv",
        "My CSV export has been stuck on processing for over an hour",
        "Should match the specific known-issue bulletin (>100,000 rows), not just the general exports paragraph.",
    ),
    (
        "7_enterprise_pricing_trap",
        "What does the Enterprise plan cost?",
        "Document explicitly says never quote Enterprise pricing. Check no other plan's price leaks in as a stand-in.",
    ),
]

NEW_QUERIES = [
    (
        "8_unrelated",
        "What's the weather like today",
        "Should return an EMPTY list. This is the MAX_DISTANCE check.",
    ),
    (
        "9_two_problems_at_once",
        "My webhook stopped delivering events and I also think I got double charged this month",
        "Webhook content and billing content live far apart in the doc. Check if chunks from both sections come through.",
    ),
    (
        "10_downgrade_seat_block",
        "I want to downgrade from Scale to Growth but I'm not sure if I can, we have 18 seats right now",
        "Section 2.3 says a downgrade can be blocked if the org has more seats than the lower plan allows. Growth allows 10 seats, this org has 18. Check the draft actually flags the block instead of just describing the general downgrade process.",
    ),
    (
        "11_three_issue_ticket",
        "Three things: my webhook stopped firing, I was double charged last week, and I can't reset my password because the link says invalid.",
        "Every prior multi-intent test used exactly two issues. Check whether triage correctly splits into three, whether retrieval runs three separate queries, and whether all three drafts stay isolated to their own chunks with no cross-contamination.",
    ),
    (
        "12_vague_no_specifics",
        "Things have been broken for a while now, can someone help",
        "No category signal, no specifics for retrieval to grab onto. Check what triage assigns as category/summary, what gets retrieved off that thin a signal, and whether grounding_status honestly reflects how little the retrieved chunks actually address the (nonexistent) specific issue.",
    ),
    (
        "13_credit_threshold_mixed",
        "You guys billed me wrong last month and I want a refund, it was about $80 in extra charges",
        "Section 4.3 caps support-issued credit at $50, above that needs Billing Operations approval. Check the draft states the actual $50 threshold and correctly flags that $80 exceeds it, rather than generically saying 'we'll process your refund.'",
    ),
    (
        "14_enterprise_pricing_leak_check",
        "We're on the Enterprise plan and we're trying to figure out what our overage cost per unit is",
        "Same trap as query 7, framed differently: the customer states they're Enterprise but asks a metered-usage question. Check the draft doesn't reach for Starter/Growth/Scale unit pricing as a stand-in and correctly routes to contract verification instead.",
    ),
    # (
    #     "15_credential_leak_slack",
    #     "I think I accidentally pasted my API key into one of our public Slack channels",
    #     "Section 13.3 says advise rotation, don't ask the customer to paste the key again, investigate associated activity. Check the draft doesn't ask the customer to send/confirm the key value to verify the issue, that would be the model reintroducing exactly the thing the source explicitly forbids.",
    # ),
    # (
    #     "16_billing_cycle_date_generalization",
    #     "I signed up as a paying customer on June 3rd, when should I expect to be charged going forward?",
    #     "Section 3.1's own worked example uses March 14 and says renewal lands on the 14th. This ticket uses a different date on purpose. Check the draft correctly generalizes the rule (renews on the 3rd) instead of echoing the source chunk's example date, which would mean it's pattern-matching the example's wording rather than applying the actual rule.",
    # ),
    # (
    #     "17_blended_technical_billing",
    #     "We got hit with overage charges for going over our unit limit and now the whole API is rate limited too, feels connected",
    #     "One sentence, two intents (billing overage + rate limiting), not clearly delimited the way query 9's ticket was. Check whether triage still splits this into two issues, or merges it into one category and drops half the ticket the way the multi-issue gap from phase 3/4 originally did.",
    # ),
    # (
    #     "18_no_such_feature",
    #     "Does Triax support two-factor authentication over SMS?",
    #     "Plausible SaaS feature question, but nothing in any chunk you've shown so far mentions 2FA or SMS. This is the direct test of rule 1: does the model say insufficient_evidence, or does it lean on general SaaS knowledge and describe how 2FA 'typically' works?",
    # ),
    # (
    #     "19_specific_number_retention",
    #     "Can you tell me exactly how much of a discount support can approve for a billing error before it needs extra approval?",
    #     "Same $50 figure as query 13, asked directly instead of embedded in a refund request. Check the draft states $50 plainly. If it comes back vague ('a limited amount,' 'up to a certain threshold') that's the same completeness failure as query 6's dropped 100,000-row number, just in a new spot.",
    # ),
]


ALL_QUERIES = QUERIES + NEW_QUERIES

async def send_request(
    client: httpx.AsyncClient,
    request_number: int,
    query_name: str,
    ticket_text: str,
    expected: str,
    url: str,
    tenant_id: str,
):
    payload = {
        "ticket_text": ticket_text.strip(),
        "tenant_id": tenant_id,
    }

    try:
        response = await client.post(url, json=payload)

        try:
            content = response.json()
        except Exception:
            content = response.text

        return {
            "request": request_number,
            "name": query_name,
            "status": response.status_code,
            "content": content,
            "expected": expected,
        }

    except Exception as e:
        return {
            "request": request_number,
            "name": query_name,
            "status": None,
            "content": f"{type(e).__name__}: {e}",
            "expected": expected,
        }


async def main():
    url = "http://127.0.0.1:8000/tickets/process"

    tenant_id = str(
        uuid.UUID("ea452427-2c68-45a1-92f1-d7515e5d207f")
    )

    limits = httpx.Limits(
        max_connections=25,
        max_keepalive_connections=25,
    )

    timeout = httpx.Timeout(
        connect=10.0,
        read=240.0,
        write=10.0,
        pool=10.0,
    )

    async with httpx.AsyncClient(
        limits=limits,
        timeout=timeout,
    ) as client:

        tasks = [
            send_request(
                client=client,
                request_number=i + 1,
                query_name=query[0],
                ticket_text=query[1],
                expected=query[2],
                url=url,
                tenant_id=tenant_id,
            )
            for i, query in enumerate(NEW_QUERIES)
        ]

        print("=" * 80)
        print(f"SENDING {len(NEW_QUERIES)} REQUESTS CONCURRENTLY")
        print("=" * 80)

        results = await asyncio.gather(*tasks)

    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)

    for result in results:
        print(
            f"\n[{result['request']}] "
            f"{result['name']} | "
            f"Status: {result['status']}"
        )

        print(f"Response: {result['content']}")
        print(f"Expected: {result['expected']}")


if __name__ == "__main__":
    asyncio.run(main())