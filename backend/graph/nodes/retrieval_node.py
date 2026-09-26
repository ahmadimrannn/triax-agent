from graph.state.state import AgentState
from tools.database.retrieve_chunks import retrieve_document_chunks
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

async def retrieval_node(state: AgentState):
    """ 
        Takes the ticket and category from triage and then retrieves the top k chunks from the database
    """

    tenant_id = state.get("tenant_id")
    issues = state.get("issues")

    all_chunks = []
    for issue in issues:
        category = issue.get('category')
        summary = issue.get("summary")

        query = f"{summary}, Category: {category}"

        try:
            chunks = await retrieve_document_chunks(
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

        for chunk in chunks:
            chunk["source_category"] = category

        all_chunks.extend(chunks)

    return {
        "retrieved_results": all_chunks
    }