import asyncio
import difflib

import httpx
import os
from dotenv import load_dotenv

load_dotenv()

tenant_id = os.getenv("TENANT_ID")


URL = "http://localhost:8000/tickets/process"
TENANT_ID = tenant_id
TIMEOUT = 300

TICKETS = [
    ("A1", "hey my webhooks stopped firing since yesterday, nothing hits our endpoint anymore and we are losing events"),
    ("A4", "why does my dashboard say ive used 80 percent of my plan when i barely call the api"),
    ("A5", "cant log in. it says invalid credentials but i literally just reset my password"),
    ("A7", "someone we dont know logged into our account last night, we are worried"),
    ("A9", "theres a charge on my card i dont recognize from you guys"),
    ("M1", "our webhooks have been failing since yesterday, and also do you give a discount for paying annually"),
    ("A3", "getting 429 errors on and off, is there some limit im hitting or what"),
    ("A8", "the signature check on your webhook payloads keeps failing on our side"),
]


def show(ticket_id, ticket_text, data):
    retrieved = data["retrieved_results"]

    print("\n" + "=" * 80)
    print(f"TICKET {ticket_id}")
    print(f"TEXT: {ticket_text}")
    print("=" * 80)

    for d in data["draft_results"]:
        key = str(d["issue_id"])
        chunks = retrieved.get(key, [])

        print(
            f"\nISSUE {key}"
            f" | category={d['category']}"
            f" | grounding={d['grounding_status']}"
            f" | cited={len(d['citations'])}"
        )

        print("\n--- DRAFT ---")
        print(d["draft_text"] or "[EMPTY]")

        print("\n--- UNCOVERED ASPECTS ---")
        print(d["uncovered_aspects"] or "[NONE]")

        print(f"\n--- RETRIEVED CHUNKS ({len(chunks)}) ---")

        here = {c["chunk_id"]: c for c in chunks}

        elsewhere = {
            c["chunk_id"]: k
            for k, cs in retrieved.items()
            if k != key
            for c in cs
        }

        for c in chunks:
            print(f"\n[{c['chunk_id']}] distance={c['distance']:.4f}")
            print(c.get("text", "[NO TEXT RETURNED]"))

        print("\n--- CITATIONS ---")

        for cited in d["citations"]:
            if cited in here:
                c = here[cited]
                print(f"\nCITED: {cited}")
                print(f"distance={c['distance']:.4f}")
                print(c.get("text", "[NO TEXT RETURNED]"))

            elif cited in elsewhere:
                print(
                    f"\nCITED: {cited}"
                    f" -> retrieved for DIFFERENT issue {elsewhere[cited]}"
                )

            else:
                pool = list(here) + list(elsewhere)

                best = difflib.get_close_matches(
                    cited,
                    pool,
                    n=1,
                    cutoff=0.0,
                )

                ratio = (
                    difflib.SequenceMatcher(
                        None,
                        cited,
                        best[0],
                    ).ratio()
                    if best
                    else 0.0
                )

                print(
                    f"\nCITED: {cited}"
                    f" -> NOT RETRIEVED"
                    f" | closest={best[0] if best else None}"
                    f" | similarity={ratio:.2f}"
                )


async def main():
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for ticket_id, ticket_text in TICKETS:
            resp = await client.post(
                URL,
                json={
                    "tenant_id": TENANT_ID,
                    "ticket_text": ticket_text,
                },
            )

            if resp.status_code != 200:
                print(
                    f"\n{ticket_id}: "
                    f"HTTP {resp.status_code} "
                    f"{resp.text[:150]}"
                )
                continue

            show(ticket_id, ticket_text, resp.json())


if __name__ == "__main__":
    asyncio.run(main())