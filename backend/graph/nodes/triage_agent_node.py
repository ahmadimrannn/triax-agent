from graph.state.state import AgentState
from config.llm import model
from graph.schemas.schemas import TriageAgentSchema
from graph.prompts.prompts import generate_triage_agent_prompt
from tools.database.ticket_actions import write_ticket
from langfuse import observe
from langfuse_config.handler import langfuse
import logging

logger = logging.getLogger(__name__)


triage_structured_llm = model.with_structured_output(TriageAgentSchema)

@observe()
async def triage_agent_node(state: AgentState):
    """
    Classifies an incoming support ticket using structured LLM output
    and persists the ticket with its classification.
    """

    tenant_id = state["tenant_id"]
    ticket_text = state["ticket_text"]

    prompt = generate_triage_agent_prompt(ticket_text)

    try:
        response = await triage_structured_llm.ainvoke(prompt)

        category = response.category
        urgency = response.urgency
    except Exception as e:
        langfuse.update_current_span(
            level="ERROR",
            status_message=str(e),
        )
        logger.exception(
            "Triage classification failed | tenant_id=%s",
            tenant_id,
        )
        raise RuntimeError(
            "Triage classification failed."
        ) from e

    try:
        ticket_id = await write_ticket(
            ticket_text=ticket_text,
            tenant_id=tenant_id,
            category=category,
            urgency=urgency,
        )

    except Exception as e:
        langfuse.update_current_span(
            level="ERROR",
            status_message=str(e),
        )
        logger.exception(
            "Failed to persist ticket | tenant_id=%s",
            tenant_id,
        )
        raise RuntimeError(
            "Failed to persist ticket."
        ) from e

    logger.info(
        "Ticket created | tenant_id=%s ticket_id=%s category=%s urgency=%s",
        tenant_id,
        ticket_id,
        category,
        urgency,
    )

    return {
        "ticket_id": ticket_id,
        "category": category,
        "urgency": urgency,
    }