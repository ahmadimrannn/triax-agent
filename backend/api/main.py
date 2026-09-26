import hashlib
import os
import uuid
from uuid import UUID
from dotenv import load_dotenv
from pydantic import BaseModel
import boto3
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, UploadFile, HTTPException
from http import HTTPStatus

from tools import db_pool
from tools.db_pool import init_db_pool, close_db_pool

from graph.graph_executor import execute_graph
from graph.graph_builder import build_graph

from utils.chunk_text import chunk_text
from utils.get_embeddings import get_embeddings
from utils.extract_text import extract_text


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pool()
    app.state.graph = build_graph()
    yield
    await close_db_pool()

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="Triax Agent - Agentic AI System for Customer Support", lifespan=lifespan)


class ProcessTicketRequest(BaseModel):
    tenant_id: str
    ticket_text: str


ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")
ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
r2 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT_URL,
    aws_access_key_id=ACCESS_KEY_ID,
    aws_secret_access_key=SECRET_ACCESS_KEY,
    region_name="auto",
)

@app.post("/documents/upload")
async def upload_document(
    file: UploadFile,
    title: str,
    tenant_id: UUID,
):
    try:
        file_bytes = await file.read()

        if not file_bytes:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty.",
            )

        content_hash = hashlib.sha256(file_bytes).hexdigest()

        # Check whether this tenant already has this exact document.
        existing = await db_pool.fetch_one(
            """
            SELECT id
            FROM documents
            WHERE tenant_id = %s
              AND content_hash = %s
            """,
            (tenant_id, content_hash),
        )

        if existing:
            raise HTTPException(
                status_code=409,
                detail="File already exists.",
            )

        # Store the original document.
        r2_key = f"/tenants/{tenant_id}/docs/{file.filename}"

        r2.put_object(
            Bucket="triax-tenant-docs",
            Key=r2_key,
            Body=file_bytes,
        )

        # Create the document record.
        document_id = await db_pool.insert_and_return_id(
            """
            INSERT INTO documents (tenant_id, title, source, content_hash
            )
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (
                tenant_id,
                title,
                r2_key,
                content_hash,
            ),
        )

        # Extract text and create chunks.
        text = extract_text(file_bytes, file.filename)
        chunks = chunk_text(text)

        # Generate embeddings and store chunks.
        for chunk_index, chunk in enumerate(chunks):
            chunk_text_value = chunk['text']

            embedding = await get_embeddings(chunk_text_value)

            await db_pool.execute(
                """
                INSERT INTO document_chunks (tenant_id, document_id, chunk_text, embedding, chunk_index)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    tenant_id,
                    document_id,
                    chunk_text_value,
                    embedding,
                    chunk_index,
                ),
            )

        return {
            "document_id": document_id,
            "chunks_created": len(chunks),
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Document upload failed | tenant_id=%s filename=%s",
            tenant_id,
            file.filename,
        )
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Failed to upload the document.",
        )

@app.post("/tickets/process")
async def process_ticket(
    request: Request,
    payload: ProcessTicketRequest,
):
    thread_id = str(uuid.uuid4())

    try:
        return await execute_graph(
            graph=request.app.state.graph,
            ticket_text=payload.ticket_text,
            tenant_id=payload.tenant_id,
            thread_id=thread_id,
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Ticket processing failed | thread_id=%s tenant_id=%s",
            thread_id,
            payload.tenant_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to process the ticket.",
        )
    