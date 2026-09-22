import hashlib
from uuid import UUID
from fastapi import FastAPI, UploadFile, HTTPException
from http import HTTPStatus
from tools import db_pool
import boto3
from dotenv import load_dotenv
import os

from utils.chunk_text import chunk_text
from utils.get_embeddings import get_embeddings
from utils.extract_text import extract_text

load_dotenv()

app = FastAPI(title="Triax Agent - Agentic AI System for Customer Support")

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
async def upload_document(file: UploadFile, title: str, tenant_id: UUID):
    try:

        file_bytes = await file.read()

        content_hash = hashlib.sha256(file_bytes).hexdigest()

        # Check if this tenant already has a document with this exact hash.
        existing = db_pool.fetch_one(
            "SELECT id FROM documents WHERE tenant_id = %s AND content_hash = %s",
            (str(tenant_id), content_hash),
        )
        if existing:
            raise HTTPException(status_code=409, detail="File already exists")

        r2_key = f"/tenants/{tenant_id}/docs/{file.filename}"
        r2.put_object(Bucket="triax-tenant-docs", Key=r2_key, Body=file_bytes)

        document_id = db_pool.insert_and_return_id(
            "INSERT INTO documents (tenant_id, title, source, content_hash) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (str(tenant_id), title, r2_key, content_hash),
        )

        # Decode the raw bytes into text, chunk it, embed each chunk, insert it.
        text = extract_text(file_bytes, file.filename)
        chunks = chunk_text(text)

        for chunk_index, chunk in enumerate(chunks):
            embedding = get_embeddings(chunk)

            db_pool.execute(
                """
                INSERT INTO document_chunks
                (tenant_id, document_id, chunk_text, embedding, chunk_index)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    tenant_id,
                    document_id,
                    chunk,
                    embedding,
                    chunk_index,
                ),
            )

        return {"document_id": document_id, "chunks_created": len(chunks)}
    except HTTPException as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload the document. Error occured while uploading the document. Error: {e}"
        )
    