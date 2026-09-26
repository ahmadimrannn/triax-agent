import logging
from uuid import UUID

from tools.db_pool import insert_and_return_id, execute

logger = logging.getLogger(__name__)


async def write_ticket(ticket_text: str, tenant_id: UUID, category: str, urgency: str):
    try:
        return await insert_and_return_id(
            """
            INSERT INTO tickets (body, tenant_id, category, urgency)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (
                ticket_text,
                tenant_id,
                category,
                urgency,
            ),
        )

    except Exception:
        logger.exception(
            "Failed to insert ticket in the database.",
            extra={
                "tenant_id": tenant_id,
                "category": category,
                "urgency": urgency,
            },
        )
        raise


async def write_ticket_issues(ticket_id: UUID, issues: list[dict]):
    """
        Writes one row per issue into ticket_issues. Called once per ticket,
        right after the ticket itself is written, with every issue triage
        found, including whichever one was picked as primary -- so
        ticket_issues is never missing the primary issue's own row.
    """

    try:
        for issue in issues:
            await execute(
                """
                    INSERT INTO ticket_issues (ticket_id, category, urgency, summary)
                    VALUES (%s, %s, %s, %s)
                """,
                (
                    ticket_id,
                    issue['category'],
                    issue['urgency'],
                    issue['summary'],
                ),
            )

    except Exception:
        logger.exception(
            "Failed to insert ticket_issue in the database.",
            extra={
                "ticket_id": ticket_id,
                "issues": issues,
            },
        )
        raise
