import logging
from uuid import UUID

from tools.db_pool import insert_and_return_id

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