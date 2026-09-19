# Triax Agent — Phased Build Plan

Multi-tenant AI customer support agent. Triage -> retrieval -> draft -> confidence
gate -> human approval if needed. Every tenant's docs and tickets isolated at the
database level. Real multi-agent LangGraph orchestration, not a single-prompt
chatbot with a RAG wrapper.

Stack: LangGraph for the pipeline, Postgres (Neon, pgvector) for tickets, tenant
data, and vector storage, same interrupt/resume HITL pattern proven in SentryLoop,
Langfuse for tracing, a judge-based eval set built from real past-resolved tickets.

Three stages, same split you used for Runa: V1 (single tenant, full pipeline
working end to end), V1.5 (multi-tenant isolation proven across 2-3 fake tenants),
V2 (dashboard, SaaS controls, billing-ready usage tracking).

---

## V1 — single tenant, full pipeline working end to end

### Phase 1 — project setup and schema
- Repo scaffold, Postgres (Neon) connection, pgvector extension enabled
- Core tables: `tenants` (one hardcoded row for now), `tickets`, `documents`,
  `document_chunks` (with `embedding VECTOR`), `proposals`
- `tenant_id` column on every table from day one, even with only one tenant,
  so V1.5 isn't a rewrite, just enforcement
- Shared DB connection pool module (psycopg 3), same pattern as SentryLoop's
  `tools/db.py`
- Definition of done: schema live in Neon, a fake ticket and a fake doc chunk
  can be inserted and read back through the pool

### Phase 2 — knowledge base ingestion
- Doc upload path (plain text/markdown files to start, no PDF parsing yet)
- Chunking strategy (fixed size with overlap, nothing fancy for V1)
- Embedding model decision needed here: hosted API (OpenAI/Cohere embeddings)
  vs local `sentence-transformers` like SentryLoop's memory phase. Local means
  no per-call cost and no rate limit, but adds deploy-size/runtime weight if
  you're on Vercel again. Decide before writing the ingestion script, not after.
- Embeddings written to `document_chunks` for the one tenant
- Definition of done: a real doc set (10-20 chunks) embedded and confirmed
  retrievable by a manual vector similarity query

### Phase 3 — triage agent
- First LangGraph node: reads incoming ticket text, classifies category and
  urgency via structured LLM output (forced enum, not free text — same lesson
  SentryLoop learned the hard way with severity/route)
- `tickets` table gets `category`, `urgency` columns written by this node
- Definition of done: 10 real or realistic tickets classified, manually checked
  against what you'd actually call them

### Phase 4 — retrieval agent
- Second node: takes the ticket + category from triage, runs vector search
  against `document_chunks` scoped to `tenant_id`
- Top-K chunks returned, similarity threshold decided the same empirical way
  SentryLoop's MAX_DISTANCE was tuned — gather real distances first, including
  at least one genuinely unrelated query as an anchor, before picking a number
- Definition of done: retrieval returns the right chunks for tickets you know
  the answer to, and returns nothing/low-confidence for a ticket your docs
  don't cover

### Phase 5 — drafting agent
- Third node: writes a proposed resolution using the ticket + retrieved chunks
  as grounding, explicitly instructed not to answer from outside the retrieved
  context
- This is where you decide how strict grounding is — an ungrounded but
  plausible-sounding draft is worse than no draft, since it's the thing most
  likely to slip past a rushed human reviewer
- Definition of done: drafts for the same 10 test tickets, manually graded for
  whether they actually used the retrieved content or hallucinated around it

### Phase 6 — confidence gate and guardrails
- A node (or a scoring step attached to drafting) that decides: send
  automatically, or hold for human review. Confidence needs a real signal —
  retrieval similarity score, an explicit LLM self-rated confidence, or both.
  Don't ship this on LLM self-rated confidence alone; that's the same
  self-reported-progress trap SentryLoop had to close for route/severity
- Guardrail: nothing gets sent to a real customer from inside this pipeline
  without going through the gate first — no code path skips it
- Tool/LLM call resilience wrapper, retries with backoff, same
  `utils/resilience.py` pattern as SentryLoop
- Definition of done: forced test where a low-confidence draft is provably
  routed to review and a high-confidence one is provably auto-sent (or would
  be, pending Phase 7's actual send mechanism)

### Phase 7 — HITL interrupt/resume
- Reuse SentryLoop's proven pattern: `interrupt()` inside the drafting/gate
  node, Postgres checkpointing so the graph actually pauses and survives a
  restart, `Command(resume=...)` to continue
- Approval channel for V1: keep it as simple as SentryLoop's email pattern
  (signed HMAC approve/reject links) rather than building a UI yet — the UI is
  V2 scope
- Same single-use guard SentryLoop needed: an approval decision can only be
  applied once, checked at the DB write, not just trusted from the request
- Definition of done: a paused proposal survives a process restart, gets
  approved via the email link, and the graph resumes and completes correctly
  — verified by diffing the resumed output against what was drafted pre-pause,
  same check SentryLoop used to catch its regenerate-on-resume bug

### Phase 8 — observability and cost tracking
- Langfuse tracing wired across all three agent calls (triage, retrieval,
  drafting) plus the gate decision
- Token usage logged per ticket, tagged with `tenant_id` even though V1 has
  only one tenant — this field is dead weight now and load-bearing in V1.5,
  wire it now while it's cheap
- Definition of done: a full ticket run traceable end to end in Langfuse, with
  a real token count attached

### Phase 9 — evals and demo
- Eval set built from real past-resolved tickets (yours, or realistic
  synthetic ones if you don't have a real support backlog — say which, since
  a judge trained against synthetic ground truth is weaker evidence in a
  portfolio piece than SentryLoop's real-bug eval set was)
- Judge prompt scoring draft quality against the known-good resolution,
  3-bucket like SentryLoop's (correct/partial/wrong) rather than a raw
  pass/fail
- Minimal real demo UI (not Postman), submit a ticket, watch it move through
  triage -> retrieval -> draft -> gate -> (auto-sent or pending review)
- Deploy (backend + frontend as separate services, same split SentryLoop used)
- **V1 checkpoint**: working single-tenant agent, real docs, real eval score,
  demoable end to end. Decide here whether V1.5/V2 are worth building before
  committing more weeks — same checkpoint discipline you used on Runa.

---

## V1.5 — multi-tenant isolation proven

### Phase 10 — real tenant model
- `tenants` table becomes real (not a hardcoded row), tenant creation flow
  (even if it's just a script, not a UI yet)
- Row-level `tenant_id` scoping enforced on every query that touches tickets,
  documents, or `document_chunks` — audit every existing query from Phases
  1-9 for this, don't assume it was already scoped correctly just because the
  column existed

### Phase 11 — tenant onboarding workflow
- A real (if manual) path to onboard a second and third tenant: upload their
  docs, run ingestion scoped to their `tenant_id`, confirm their vector search
  never returns another tenant's chunks

### Phase 12 — isolation regression tests
- Automated tests, not manual spot checks: given tenant A's ticket, assert
  zero chunks from tenant B or C ever appear in retrieval results, across all
  3 fake tenants
- This is the phase most likely to surface a real bug — a single unscoped
  query anywhere in Phases 2-9 is a full tenant data leak, not a cosmetic bug.
  Budget real time here, don't treat it as a formality.

### Phase 13 — per-tenant config
- Confidence gate threshold, category taxonomy, and retrieval top-K become
  per-tenant settings instead of hardcoded constants
- Token/cost tracking rolled up per tenant (sum across their tickets), not
  just per ticket — this is the number V2's billing phase needs
- **V1.5 checkpoint**: 3 fake tenants, proven isolation, per-tenant config
  working. This is the real proof-of-multi-tenancy deliverable.

---

## V2 — dashboard and SaaS controls

### Phase 14 — dashboard auth
- Tenant admin login, scoped so a logged-in admin can only ever see their own
  tenant's data — this is the UI-layer version of Phase 12's isolation test,
  and needs its own explicit check, not an assumption that the backend
  scoping already covers it

### Phase 15 — review queue UI
- Real interface for a human reviewer to see pending proposals, read the
  ticket + retrieved context + draft, and approve/reject — replaces the
  email-link flow from Phase 7 as the primary path (email can stay as a
  notification, not the only decision mechanism)

### Phase 16 — knowledge base management UI
- Upload, view, and delete docs per tenant through the dashboard instead of a
  script
- Re-embedding on doc update/delete, with old chunks actually removed, not
  left as stale dead rows a future retrieval could still surface

### Phase 17 — config UI
- Confidence threshold, category taxonomy, and retrieval settings from
  Phase 13 exposed as real settings a tenant admin can change, not just
  DB columns

### Phase 18 — usage and billing-ready tracking
- Per-tenant dashboard view of ticket volume, token cost, and auto-send vs
  human-review split — the reporting layer on top of Phase 13's cost rollup
- "Billing-ready" means the numbers are correct and queryable per tenant per
  billing period, not that you're wiring an actual payment processor here

### Phase 19 — automated eval regression on config change
- When a tenant edits their docs or confidence threshold through the
  dashboard, an automated eval run against that tenant's data confirms
  quality didn't silently regress before the change goes live
- This is the phase Runa's V2 added for the same reason (model-switch
  revalidation) — a config UI without a regression check just means tenants
  can quietly break their own pipeline with a slider

### Phase 20 — final demo and close
- Multi-tenant demo walkthrough: create a tenant, upload docs, submit tickets,
  show isolation, show the review queue, show usage tracking
- Docs, README, LinkedIn/portfolio writeup
- **V2 checkpoint**: full SaaS-shaped product, not a script with a database.

---

## Where this is most likely to go over estimate

**Phase 12 (isolation regression tests)** is the one to worry about, not the
LangGraph pipeline itself — you already know how to chain agents and gate on
confidence from SentryLoop. What you haven't done before on this project is
prove a shared vector index genuinely can't leak across tenants under real
query patterns, and that's exactly the kind of bug that looks fine in a demo
and fails the first time someone actually audits it.

**Phase 6 (confidence gate)** is the second risk. A gate that's too
permissive defeats the point of the whole project (auto-sending bad drafts to
real customers); a gate that's too conservative means nothing ever
auto-sends and the "handled automatically without losing control" pitch has
no evidence behind it. Budget real tuning time here with real distance/score
data, same way SentryLoop's MAX_DISTANCE only got trusted after 15 real data
points across related and unrelated cases — don't ship on a guessed
threshold.

## Timeline at ~4 hrs/day

- V1: ~5-6 weeks (~120-150 hrs) — 3 chained agents plus RAG plus a real HITL
  gate is more moving parts than Runa's single-agent voice pipeline, but no
  dynamic step-count loop like SentryLoop's investigation phase, so it should
  land closer to SentryLoop's 5-week pace than run long
- V1.5: ~1.5-2 weeks (~30-40 hrs)
- V2: ~2.5-3 weeks (~50-60 hrs)
- Total: ~9-11 weeks (~200-250 hrs)

Same as Runa: treat the end of V1 as the real checkpoint. A working
single-tenant agent with a real eval score is a complete, demoable project on
its own — decide whether V1.5/V2 are worth it after you're standing there,
not before.