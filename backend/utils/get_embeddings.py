import os

import numpy as np
from dotenv import load_dotenv
from huggingface_hub import AsyncInferenceClient

from utils.resilience import with_resilience


load_dotenv()


HF_TOKEN = os.getenv("HF_TOKEN")

_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_client = AsyncInferenceClient(
    provider="hf-inference",
    token=HF_TOKEN,
)


@with_resilience()
async def get_embeddings(chunk: str) -> list[float]:
    if not chunk:
        raise ValueError("Cannot generate an embedding for empty text.")

    raw = await _client.feature_extraction(
        chunk,
        model=_MODEL,
    )

    vector = np.asarray(raw, dtype=np.float32)

    if vector.ndim > 1:
        vector = vector.mean(axis=0)

    if vector.ndim != 1:
        raise ValueError(
            f"Unexpected embedding shape: {vector.shape}"
        )

    norm = np.linalg.norm(vector)

    if norm == 0:
        raise ValueError(
            "Embedding model returned a zero vector."
        )

    vector = vector / norm

    return vector.tolist()


if __name__ == "__main__":
    import asyncio

    async def main():
        chunk = "my name is ahmad"
        embeddings = await get_embeddings(chunk)

        print("Length of embeddings:", len(embeddings))
        print(embeddings)

    asyncio.run(main())
