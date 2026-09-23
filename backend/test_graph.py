import asyncio
from uuid import UUID

from graph.graph_builder import build_graph
from graph.graph_executor import execute_graph


async def main():
    graph = build_graph()

    result = await execute_graph(
        graph=graph,
        ticket_text="I was charged twice for my subscription.",
        tenant_id=UUID("e988b45c-2a34-450f-964d-5f0afd0ed33f"),
    )

    print("\nFINAL STATE:")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())