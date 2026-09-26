# Triax Agent

A multi-tenant AI customer support agent that reads incoming tickets, researches the answer against a tenant's own documentation, drafts a reply, and only sends it automatically when it's actually confident, otherwise it holds for a human to approve.

This is not a single prompt wrapped around a vector database. It's a real multi-agent pipeline built on LangGraph, where each step, triage, retrieval, drafting, and the confidence gate, is its own node with its own responsibility, its own failure mode, and its own tests.

## Table of Contents

- [Why this exists](#why-this-exists)
- [How a ticket moves through the system](#how-a-ticket-moves-through-the-system)
- [Key features](#key-features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Multi-tenancy](#multi-tenancy)
- [Getting started](#getting-started)
- [Project structure](#project-structure)
- [Evaluation](#evaluation)
- [Known limitations](#known-limitations)
- [License](#license)

## Why this exists

Most "AI support agent" demos are one LLM call with some retrieved text stuffed into the prompt. That works for a screenshot. It falls apart the moment a ticket mentions two unrelated problems, or the retrieved context is wrong, or the model is confident and wrong at the same time, which is the actual failure mode that costs a real business money and trust.

Triax is built around three constraints that most demos skip:

- **A ticket can contain more than one problem.** A customer reporting a broken webhook and a duplicate charge in the same message is one ticket, not one issue. Triax classifies and researches each issue separately instead of collapsing them into whichever one the model noticed first.
- **A confident-sounding answer is not the same as a correct one.** Nothing gets sent to a real customer without passing a confidence gate first. Low-confidence drafts are held for a human, not shipped anyway.
- **Every tenant's data is isolated at the database level**, not just filtered in application code. One tenant's documents and tickets should be structurally unreachable from another tenant's queries, not just excluded by a `WHERE` clause someone might forget to add.

## How a ticket moves through the system

```
Ticket comes in
      |
      v
+-------------+     classifies the ticket into one or more
|   Triage    |     independent issues, each with its own
|             |     category, urgency, and summary
+------+------+
       |
       v
+-------------+     runs a separate vector search per issue,
|  Retrieval  |     scoped to the tenant, against that tenant's
|             |     own ingested documentation
+------+------+
       |
       v
+-------------+     writes a proposed reply per issue, grounded
|   Drafting  |     only in what retrieval actually returned,
|             |     not the model's general knowledge
+------+------+
       |
       v
+-------------+     scores confidence using retrieval strength
| Confidence  |     and the model's own self-rated confidence,
|    Gate     |     never one signal alone
+------+------+
       |
   +---+----+
   v        v
 High      Low
confidence confidence
   |        |
   v        v
Auto-sent  Held for human review
           (interrupt/resume, resolved
            via a signed approval link)
```

Every step of this is traced end to end in Langfuse, so a support engineer, or a curious reviewer, can open any ticket and see exactly which chunks were retrieved, what the model was actually shown, and why the gate made the call it made. Nothing about the decision is a black box after the fact.

## Key features

- **Multi-agent LangGraph pipeline.** Triage, retrieval, drafting, and the confidence gate are separate nodes with their own state, not one long prompt.
- **Multi-intent ticket handling.** A ticket with two unrelated problems produces two separately classified, separately researched, separately drafted issues, tracked in their own table.
- **Confidence-gated auto-send.** Confidence comes from retrieval similarity and an explicit model self-rating together, never from self-rated confidence alone.
- **Human-in-the-loop via interrupt and resume.** A held ticket survives a process restart, gets approved through a signed, single-use link, and resumes exactly where it paused, verified by diffing the resumed output against the original draft.
- **Row-level multi-tenant isolation**, enforced at the database layer and checked by automated regression tests, not manual spot checks, across every query that touches ticket, document, or chunk data.
- **Per-tenant configuration.** Confidence threshold, category taxonomy, and retrieval depth are settings per tenant, not constants shared across every customer.
- **Full observability.** Every agent call and every gate decision is traced in Langfuse with real token counts, tagged by tenant from day one.
- **A real review dashboard**, not a Postman collection: a tenant admin can log in, see only their own tenant's data, manage their knowledge base, review pending proposals, and see usage and cost broken down per tenant.
- **Automated eval regression on config change.** If a tenant edits their docs or their confidence threshold through the dashboard, an eval run confirms answer quality didn't silently regress before the change goes live.

## Architecture

| Layer | Responsibility |
|---|---|
| Triage node | Classifies incoming ticket text into one or more issues, each with a category, urgency, and a standalone summary used later for retrieval |
| Retrieval node | Runs one vector search per issue, scoped to `tenant_id`, against that tenant's `document_chunks` |
| Drafting node | Writes a proposed reply per issue, grounded only in the chunks retrieval actually returned |
| Confidence gate | Combines retrieval similarity and model self-confidence into a single send/hold decision, with no code path that bypasses it |
| HITL layer | Pauses the graph on a held ticket via Postgres checkpointing, resumes it on approval through a signed HMAC link |
| Dashboard | Tenant-scoped admin UI: review queue, knowledge base management, per-tenant config, usage and cost reporting |

Every table (`tickets`, `ticket_issues`, `documents`, `document_chunks`) carries `tenant_id` from the very first schema migration, even before multi-tenancy was actually exercised, so proving isolation later was enforcement work, not a rewrite.

## Tech stack

| Concern | Choice |
|---|---|
| Agent orchestration | LangGraph |
| Database | Postgres (Neon), with the `pgvector` extension |
| Vector search | HNSW index, cosine distance |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Tracing | Langfuse |
| HITL persistence | LangGraph's interrupt/resume with Postgres checkpointing |
| Backend | FastAPI, async throughout, psycopg 3 connection pool |
| Deployment | Backend and frontend deployed as separate services |

## Multi-tenancy

Isolation is not "the application code always adds a tenant filter." It's tested directly: given tenant A's ticket, an automated regression suite asserts that zero chunks from tenant B or C can ever appear in retrieval results, run across every tenant-scoped query in the codebase, not just the ones that looked obviously risky.

A single shared vector index across tenants doesn't automatically understand a `tenant_id` filter the way a normal indexed column does. Approximate nearest-neighbor search runs first, then the tenant filter is applied, then the result limit, which means a tenant with a small slice of a large shared table can, in principle, get weaker results than a tenant with a large slice. This is a known tuning point (raising `hnsw.ef_search` for filtered queries), documented here rather than left as a silent surprise for whoever scales this past a handful of demo tenants.

## Getting started

```bash
# clone and install
git clone <repo-url>
cd triax-agent
pip install -r requirements.txt

# environment
cp .env.example .env
# fill in: DATABASE_URL, embedding model config, Langfuse keys, HMAC secret for approval links

# database
psql "$DATABASE_URL" -f migrations/001_initial_schema.sql
psql "$DATABASE_URL" -f migrations/002_ticket_issues.sql

# run
uvicorn main:app --reload
```

<!-- Add real setup steps here once the dashboard's own install path exists -->

## Project structure

```
triax-agent/
├── backend/
│   ├── graph/
│   │   ├── nodes/          # triage, retrieval, drafting, confidence gate
│   │   ├── state/          # AgentState and related types
│   │   ├── schemas/        # structured LLM output schemas
│   │   └── prompts/        # prompt templates per node
│   ├── tools/
│   │   ├── database/       # ticket_actions, retrieve_chunks, chunking
│   │   └── db_pool.py      # shared async Postgres connection pool
│   ├── config/              # settings, LLM client config
│   └── main.py
├── frontend/                 # dashboard: review queue, KB management, config, usage
├── migrations/
└── tests/
```

## Evaluation

Draft quality is scored against real, previously resolved tickets using a judge LLM, graded on a three-bucket scale, correct, partial, or wrong, rather than a raw pass/fail, since "close but missing a caveat" and "confidently wrong" are very different failures that a binary score would hide from each other.

<!-- Fill in actual eval set size and score once Phase 9/10 (evals and demo) is run -->

## Known limitations

- Retrieval currently issues one embedding query per detected issue. It does not yet reason across issues, so two issues that are actually related (a plan downgrade that caused both a billing question and an access question) are still researched independently.
- The confidence gate's threshold is tuned empirically against real distance and confidence data, not derived analytically, and needs revisiting any time the embedding model or chunking strategy changes.
- Chunk size is currently fixed per tenant rather than tuned per document type; a knowledge base with very short, dense sections and one with long narrative sections may not be equally well served by the same setting.

## License

<!-- Choose a license and update this section -->
