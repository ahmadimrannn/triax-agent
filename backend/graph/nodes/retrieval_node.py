from graph.state.state import AgentState
from tools.database.retrieve_chunks import retrieve_document_chunks
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

async def retrieval_node(state: AgentState):
    """ 
        Takes the ticket and category from triage and then retrieves the top k chunks from the database
    """

    ticket_text = state.get("ticket_text")
    category = state.get("category")
    tenant_id = state.get("tenant_id")

    query = f"Ticket Text: {ticket_text}, Category: {category}"

    try:
        retrieved_results = await retrieve_document_chunks(
            query=query, 
            tenant_id=UUID(tenant_id)
        )

    except Exception as e:
        logger.exception(
            "Failed to retrieve results | tenant_id=%s",
            tenant_id,
        )
        raise RuntimeError(
            "Failed to retrieve results."
        ) from e

    logger.info(
        "Results Retrieved | tenant_id=%s query=%s",
        tenant_id,
        query,
    )

    return {
        "retrieved_results": retrieved_results
    }