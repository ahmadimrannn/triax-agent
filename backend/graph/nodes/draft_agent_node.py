import logging
from config.llm import model, rate_limited_ainvoke

from graph.state.state import AgentState
from graph.prompts.prompts import generate_draft_agent_prompt
from graph.schemas.schemas import DraftedAgentResolution
from tools.database.create_proposal import upsert_draft_proposal


logger = logging.getLogger(__name__)

draft_structured_llm = model.with_structured_output(DraftedAgentResolution)


def _validate_citations(citations, formatted_chunks, issue_id, tenant_name):
    """
    Keeps only citations that exactly match a chunk_id actually present in
    this issue's retrieved chunks. chunk_id may come through as a UUID
    object (e.g. straight from psycopg) even when citations are plain
    strings from the LLM's structured output, so normalize both sides
    to strings before comparing.
    """
    
    valid_ids = {str(chunk["chunk_id"]) for chunk in formatted_chunks}
    valid_citations = [c for c in citations if str(c) in valid_ids]
    invalid_citations = [c for c in citations if str(c) not in valid_ids]

    if invalid_citations:
        logger.warning(
            "Draft cited chunk_id(s) not present in this issue's retrieved "
            "chunks. issue_id=%s tenant=%s invalid=%s valid_ids=%s",
            issue_id, tenant_name, invalid_citations, list(valid_ids)
        )

    return valid_citations, bool(invalid_citations)


async def draft_agent_node(state: AgentState):
    """
        Drafts a proposal for each issue on the ticket, using that issue's
        own retrieved chunks, and persists each successful draft to the
        proposals table. One issue failing to draft does not block the
        others.
    """

    tenant_id = state.get("tenant_id")
    tenant_name = state.get("tenant_name")
    ticket_id = state.get("ticket_id")
    ticket_text = state.get("ticket_text")
    retrieved_results = state.get("retrieved_results")
    issues = state.get("issues")

    draft_results = []

    for idx, issue in enumerate(issues):
        issue_id = str(idx)
        category = issue["category"]
        urgency = issue["urgency"]
        issue_summary = issue["summary"]

        formatted_chunks = retrieved_results.get(issue_id, [])

        if not formatted_chunks:
            logger.warning(
                "No retrieved chunks for issue_id=%s category=%s tenant=%s. "
                "Drafting will run with empty context.",
                issue_id, category, tenant_name
            )

        prompt = generate_draft_agent_prompt(
            tenant_name=tenant_name,
            formatted_chunks=formatted_chunks,
            category=category,
            urgency=urgency,
            issue_summary=issue_summary,
            ticket_text=ticket_text
        )

        try:
            res = await rate_limited_ainvoke(draft_structured_llm, prompt)
            drafted = res.model_dump()

            valid_citations, had_invalid = _validate_citations(
                drafted.get("citations", []), formatted_chunks, issue_id, tenant_name
            )
            drafted["citations"] = valid_citations

            grounding_status = drafted.get("grounding_status")
            if had_invalid and not valid_citations and grounding_status != "insufficient_evidence":
                logger.warning(
                    "All citations invalid after validation, downgrading grounding_status "
                    "from %s to insufficient_evidence. issue_id=%s tenant=%s",
                    grounding_status, issue_id, tenant_name
                )
                drafted["grounding_status"] = "insufficient_evidence"
                drafted["draft_text"] = ""
                drafted["uncovered_aspects"] = (
                    (drafted.get("uncovered_aspects") or "")
                    + " [System note: original citations failed validation and were removed.]"
                ).strip()

            await upsert_draft_proposal(
                tenant_id=tenant_id,
                ticket_id=ticket_id,
                issue_id=issue_id,
                category=category,
                urgency=urgency,
                draft_text=drafted.get("draft_text"),
                citations=drafted.get("citations", []),
                grounding_status=drafted.get("grounding_status"),
                uncovered_aspects=drafted.get("uncovered_aspects"),
            )

            draft_results.append({
                "issue_id": issue_id,
                "category": category,
                "status": "ok",
                **drafted
            })

        except Exception:
            logger.exception(
                "Draft resolution failed. issue_id=%s category=%s tenant=%s",
                issue_id, category, tenant_name
            )
            draft_results.append({
                "issue_id": issue_id,
                "category": category,
                "status": "failed",
                "grounding_status": None,
                "draft_text": None,
                "citations": [],
                "uncovered_aspects": None,
            })

    return {
        "draft_results": draft_results
    }