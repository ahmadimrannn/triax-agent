from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector
from dotenv import load_dotenv
import os
from psycopg.rows import dict_row

load_dotenv()

POSTGRES_URI = os.getenv("POSTGRES_URI")

def configure_connection(conn):
    register_vector(conn)

pool = ConnectionPool(
    conninfo=POSTGRES_URI, 
    max_size=5,
    max_idle=300, 
    kwargs={
        "autocommit": True, 
        "row_factory": dict_row
    },
    check=ConnectionPool.check_connection,
    configure=configure_connection,
)

def get_db_connection():
    return pool.connection()

def fetch_one(query: str, params: tuple = ()):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()

def insert_and_return_id(query: str, params: tuple = ()):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return row["id"] if row else None

def execute(query: str, params: tuple = ()):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)