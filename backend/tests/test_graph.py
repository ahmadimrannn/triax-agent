import asyncio
from uuid import UUID

from graph.graph_builder import build_graph
from graph.graph_executor import execute_graph

import os
from dotenv import load_dotenv

load_dotenv()

tenant_id = os.getenv("TENANT_ID")


async def main():
    graph = build_graph()

    result = await execute_graph(
        graph=graph,
        ticket_text="I was charged twice for my subscription.",
        tenant_id=UUID(tenant_id),
    )

    print("\nFINAL STATE:")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())