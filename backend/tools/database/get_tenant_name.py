from uuid import UUID
import logging

from tools.db_pool import fetch_one

logger = logging.getLogger(__name__)

async def get_tenant_name(tenant_id: UUID):
    """ 
        Retrieves the tenant name using tenant_id
    """

    try:
        tenant_name = await fetch_one(
            """
                SELECT name FROM tenants
                WHERE id = %s
            """,
            (tenant_id,)
        )
        return tenant_name
    except Exception:
        logger.exception(
            "Failed to retrieve document chunks from the database.",
        )
        raise