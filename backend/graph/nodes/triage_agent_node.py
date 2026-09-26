from graph.state.state import AgentState
from config.llm import model
from graph.schemas.schemas import TriageAgentSchema
from graph.prompts.prompts import generate_triage_agent_prompt
from tools.database.ticket_actions import write_ticket, write_ticket_issues
import logging
from config.settings import URGENCY_RANK

logger = logging.getLogger(__name__)

triage_structured_llm = model.with_structured_output(TriageAgentSchema)

 
def pick_primary_issue(issues: list[dict]) -> dict:
    """
        Given a list of issues from triage, pick the one that represents the
        ticket as a whole for the tickets table's existing category/urgency
        columns. Highest urgency wins. If two issues tie on urgency, the
        first one triage returned wins, so this is deterministic instead of
        picking whichever dict happens to sort first in memory.
    """
    return max(
        issues,
        key=lambda issue: URGENCY_RANK.get(issue["urgency"], 0),
    )

async def triage_agent_node(state: AgentState):
    """
        Classifies an incoming support ticket into one or more issues using
        structured LLM output, persists the ticket (tagged with its primary
        issue's category/urgency) and persists every individual issue.
    """

    tenant_id = state["tenant_id"]
    ticket_text = state["ticket_text"]

    prompt = generate_triage_agent_prompt(ticket_text)

    try:
        response = await triage_structured_llm.ainvoke(prompt)

        issues = [issue.model_dump() for issue in response.issues]
    except Exception as e:
        logger.exception(
            "Triage classification failed | tenant_id=%s",
            tenant_id,
        )
        raise RuntimeError(
            "Triage classification failed."
        ) from e

    if not issues:
        raise RuntimeError(
            f"Triage agent returned zero issues | tenant_id={tenant_id}"
        )

    primary = pick_primary_issue(issues)

    try:
        ticket_id = await write_ticket(
            ticket_text=ticket_text,
            tenant_id=tenant_id,
            category=primary['category'],
            urgency=primary['urgency'],
        )

        await write_ticket_issues(
            ticket_id=ticket_id,
            issues=issues
        )

    except Exception as e:
        logger.exception(
            "Failed to persist ticket | tenant_id=%s",
            tenant_id,
        )
        raise RuntimeError(
            "Failed to persist ticket."
        ) from e

    logger.info(
        "Ticket created | tenant_id=%s ticket_id=%s issue_count=%d primary_category=%s",
        tenant_id,
        ticket_id,
        len(issues),
        primary["category"],
    )

    return {
        "ticket_id": ticket_id,
        "issues": issues,
    }