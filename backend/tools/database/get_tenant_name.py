from uuid import UUID
import logging

from tools.db_pool import fetch_one
from utils.resilience import with_resilience


logger = logging.getLogger(__name__)

@with_resilience()
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