import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )

from uuid import UUID

from tools.db_pool import fetch_all, init_db_pool, close_db_pool
from utils.get_embeddings import get_embeddings
from config.settings import TOP_K, MAX_DISTANCE

async def retrieve_document_chunks(query: str, tenant_id: UUID):
    """
        Retrieve top k chunks from document_chunks from the database
    """

    embedded_query = await get_embeddings(query)

    chunks = await fetch_all(
        """
            SELECT chunk_text, embedding <=> %s::vector AS distance
            FROM document_chunks
            WHERE embedding IS NOT NULL and tenant_id = %s
            ORDER BY distance ASC
            LIMIT %s
        """,
        (embedded_query, tenant_id, TOP_K)
    )

    filtered_chunks = [
        chunk for chunk in chunks
        if chunk['distance'] <= MAX_DISTANCE
    ]

    return filtered_chunks

if __name__ == "__main__":
    async def main():
        await init_db_pool()

        try:
            text = """
                I think someone got into my account without my permission
            """
            tenant_id = UUID("ea452427-2c68-45a1-92f1-d7515e5d207f")

            chunks = await retrieve_document_chunks(text, tenant_id)

            print("Length of retrieved chunks:", len(chunks))
            print("Retrieved Chunks:", chunks)

        finally:
            await close_db_pool()

    asyncio.run(main())