import asyncio
from uuid import UUID

from graph.graph_builder import build_graph
from graph.graph_executor import execute_graph


async def main():
    graph = build_graph()

    result = await execute_graph(
        graph=graph,
        ticket_text="I was charged twice for my subscription.",
        tenant_id=UUID("ea452427-2c68-45a1-92f1-d7515e5d207f"),
    )

    print("\nFINAL STATE:")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())