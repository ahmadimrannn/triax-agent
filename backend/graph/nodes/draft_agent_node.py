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
    Keep only citations that exactly match chunk_ids actually retrieved
    for this issue.

    UUID objects from PostgreSQL and strings returned by the LLM are
    normalized to strings before comparison.
    """

    valid_ids = {
        str(chunk["chunk_id"])
        for chunk in formatted_chunks
        if chunk.get("chunk_id") is not None
    }

    valid_citations = []
    invalid_citations = []

    for citation in citations or []:
        citation_str = str(citation)

        if citation_str in valid_ids:
            valid_citations.append(citation_str)
        else:
            invalid_citations.append(citation_str)

    if invalid_citations:
        logger.warning(
            "Invalid citation(s) removed | "
            "issue_id=%s tenant=%s invalid=%s valid_ids=%s",
            issue_id,
            tenant_name,
            invalid_citations,
            list(valid_ids),
        )

    return valid_citations, invalid_citations


async def draft_agent_node(state: AgentState):
    """
    Draft a proposed resolution for each issue using only that issue's
    retrieved chunks.

    Citation validation is fail-closed:
    invalid citations are removed and prevent the ticket from being
    auto-sent through the confidence gate.

    A useful draft is preserved for human review even when its citations
    fail validation.
    """

    tenant_id = state.get("tenant_id")
    tenant_name = state.get("tenant_name")
    ticket_id = state.get("ticket_id")
    ticket_text = state.get("ticket_text")
    retrieved_results = state.get("retrieved_results") or {}
    issues = state.get("issues") or []

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
                issue_id,
                category,
                tenant_name,
            )

        prompt = generate_draft_agent_prompt(
            tenant_name=tenant_name,
            formatted_chunks=formatted_chunks,
            category=category,
            urgency=urgency,
            issue_summary=issue_summary,
            ticket_text=ticket_text,
        )

        try:
            res = await rate_limited_ainvoke(
                draft_structured_llm,
                prompt,
            )

            drafted = res.model_dump()

            logger.info(
                "Raw draft output | "
                "issue_id=%s category=%s grounding=%s citations=%s "
                "draft=%r uncovered=%r",
                issue_id,
                category,
                drafted.get("grounding_status"),
                drafted.get("citations"),
                drafted.get("draft_text"),
                drafted.get("uncovered_aspects"),
            )

            valid_citations, invalid_citations = _validate_citations(
                drafted.get("citations", []),
                formatted_chunks,
                issue_id,
                tenant_name,
            )

            drafted["citations"] = valid_citations

            if invalid_citations:
                original_grounding_status = drafted.get("grounding_status")

                drafted["grounding_status"] = "insufficient_evidence"

                existing_uncovered = (
                    drafted.get("uncovered_aspects") or ""
                ).strip()

                citation_note = (
                    "One or more generated citations did not exactly match "
                    "the retrieved chunk IDs and were removed. The draft "
                    "cannot be auto-sent until its evidence is validated."
                )

                if existing_uncovered:
                    drafted["uncovered_aspects"] = (
                        f"{existing_uncovered} {citation_note}"
                    )
                else:
                    drafted["uncovered_aspects"] = citation_note

                logger.warning(
                    "Citation validation failed | "
                    "issue_id=%s category=%s "
                    "original_grounding=%s invalid=%s "
                    "valid=%s. Draft preserved for human review.",
                    issue_id,
                    category,
                    original_grounding_status,
                    invalid_citations,
                    valid_citations,
                )

            grounding_status = drafted.get("grounding_status")
            draft_text = drafted.get("draft_text") or ""
            citations = drafted.get("citations") or []

            if grounding_status == "insufficient_evidence":
                drafted["draft_text"] = ""
                drafted["citations"] = []

            elif draft_text.strip() and not citations:
                drafted["grounding_status"] = "insufficient_evidence"

                existing_uncovered = (
                    drafted.get("uncovered_aspects") or ""
                ).strip()

                citation_note = (
                    "The draft contains no valid citations to retrieved "
                    "evidence."
                )

                drafted["uncovered_aspects"] = (
                    f"{existing_uncovered} {citation_note}".strip()
                )

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

            draft_results.append(
                {
                    "issue_id": issue_id,
                    "category": category,
                    "status": "ok",
                    **drafted,
                }
            )

        except Exception as exc:
            logger.exception(
                "Draft resolution failed | "
                "issue_id=%s category=%s tenant=%s",
                issue_id,
                category,
                tenant_name,
            )

            draft_results.append(
                {
                    "issue_id": issue_id,
                    "category": category,
                    "status": "failed",
                    "grounding_status": None,
                    "draft_text": None,
                    "citations": [],
                    "uncovered_aspects": None,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    return {
        "draft_results": draft_results,
    }