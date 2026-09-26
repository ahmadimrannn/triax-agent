import logging
import uuid
from typing import Any
from uuid import UUID

from langgraph.graph.state import CompiledStateGraph

from langfuse_config.handler import langfuse_handler

logger = logging.getLogger(__name__)


async def execute_graph(
    graph: CompiledStateGraph,
    ticket_text: str,
    tenant_id: UUID,
    thread_id: str | None = None,
) -> dict[str, Any]:

    active_thread_id = thread_id or str(uuid.uuid4())

    initial_state = {
        "tenant_id": tenant_id,
        "ticket_text": ticket_text,
        "ticket_id": "",
        "category": "",
        "urgency": "",
    }

    config = {
        "configurable": {
            "thread_id": active_thread_id,
        },
        "callbacks": [langfuse_handler],
    }

    final_state: dict[str, Any] = {}

    try:
        async for state_snapshot in graph.astream(
            initial_state,
            config,
            stream_mode="values",
        ):
            ticket_id = state_snapshot.get("ticket_id")
            category = state_snapshot.get("category")
            urgency = state_snapshot.get("urgency")

            logger.info(
                "Graph state | "
                "tenant_id=%s ticket_id=%s category=%s urgency=%s",
                tenant_id,
                ticket_id,
                category,
                urgency,
            )

            final_state = state_snapshot

    except Exception:
        logger.exception(
            "Graph execution failed | thread_id=%s tenant_id=%s",
            active_thread_id,
            tenant_id,
        )
        raise

    return final_state