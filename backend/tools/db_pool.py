import os

from dotenv import load_dotenv
from pgvector.psycopg import register_vector_async
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


load_dotenv()

POSTGRES_URI = os.getenv("POSTGRES_URI")

if not POSTGRES_URI:
    raise RuntimeError("POSTGRES_URI is not configured")


pool: AsyncConnectionPool | None = None
checkpointer: AsyncPostgresSaver | None = None


async def configure_connection(conn):
    await register_vector_async(conn)


async def init_db_pool():
    global pool
    global checkpointer

    if pool is not None:
        return

    pool = AsyncConnectionPool(
        conninfo=POSTGRES_URI,
        min_size=1,
        max_size=5,
        max_idle=300,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        configure=configure_connection,
    )

    await pool.open()

    checkpointer = AsyncPostgresSaver(
        pool,
        serde=JsonPlusSerializer(),
    )

    await checkpointer.setup()


async def close_db_pool():
    global pool
    global checkpointer

    if pool is not None:
        await pool.close()

    pool = None
    checkpointer = None


def get_db_connection():
    if pool is None:
        raise RuntimeError(
            "Database pool has not been initialized. "
            "Call init_db_pool() during application startup."
        )

    return pool.connection()


async def fetch_one(
    query: str,
    params: tuple = (),
):
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchone()


async def fetch_all(
    query: str,
    params: tuple = (),
):
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchall()


async def insert_and_return_id(
    query: str,
    params: tuple = (),
):
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            row = await cur.fetchone()

            return row["id"] if row else None


async def execute(
    query: str,
    params: tuple = (),
):
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)