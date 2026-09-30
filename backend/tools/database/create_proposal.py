import logging
from psycopg.types.json import Json
from utils.resilience import with_resilience

from tools.db_pool import execute

logger = logging.getLogger(__name__)


@with_resilience()
async def upsert_draft_proposal(
    tenant_id,
    ticket_id,
    issue_id: str,
    category: str,
    urgency: str,
    draft_text: str | None,
    citations: list[str],
    grounding_status: str | None,
    uncovered_aspects: str | None,
) -> None:
    """
    Writes a draft into the proposals table. If a proposal already exists
    for this (ticket_id, issue_id) and is still in 'drafted' status, it's
    overwritten (safe to rerun this node). If it's moved past 'drafted'
    (a human or the confidence gate already acted on it), the write is
    silently ignored at the DB level and we log that it happened.
    """

    try:
        await execute(
            """
            INSERT INTO proposals (
                tenant_id, ticket_id, issue_id, category, urgency,
                draft_text, citations, grounding_status, uncovered_aspects
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticket_id, issue_id) DO UPDATE SET
                draft_text = EXCLUDED.draft_text,
                citations = EXCLUDED.citations,
                grounding_status = EXCLUDED.grounding_status,
                uncovered_aspects = EXCLUDED.uncovered_aspects,
                updated_at = now()
            WHERE proposals.status = 'drafted'
            RETURNING proposal_id
            """,
            (
                tenant_id, ticket_id, issue_id, category, urgency,
                draft_text, Json(citations), grounding_status, uncovered_aspects,
            ),
        )
    except Exception:
        logger.exception(
            "Failed to insert proposal in the database.",
            extra={
                "tenant_id": tenant_id,
                "category": category,
                "urgency": urgency,
            },
        )
        raise