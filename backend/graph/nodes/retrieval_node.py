from graph.state.state import AgentState
from tools.database.retrieve_chunks import retrieve_document_chunks
import logging

logger = logging.getLogger(__name__)

async def retrieval_node(state: AgentState):
    """
        Retrieves the top k chunks for each issue on the ticket, keyed by
        issue index so drafting can look up the right chunk set later.
    """

    tenant_id = state.get("tenant_id")
    issues = state.get("issues")

    retrieved_by_issue = {}

    for idx, issue in enumerate(issues):
        issue_id = str(idx)
        category = issue.get("category")
        summary = issue.get("summary")

        query = f"{summary}, Category: {category}"

        try:
            chunks = await retrieve_document_chunks(
                query=query,
                tenant_id=tenant_id
            )
        except Exception as e:
            logger.exception(
                "Failed to retrieve results | tenant_id=%s issue_id=%s category=%s",
                tenant_id, issue_id, category,
            )
            raise RuntimeError(
                "Failed to retrieve results."
            ) from e

        logger.info(
            "Results retrieved | tenant_id=%s issue_id=%s category=%s chunk_count=%d",
            tenant_id, issue_id, category, len(chunks),
        )

        retrieved_by_issue[issue_id] = chunks

    return {
        "retrieved_results": retrieved_by_issue
    }