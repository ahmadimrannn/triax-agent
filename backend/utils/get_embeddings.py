import os
import numpy as np
from dotenv import load_dotenv
from huggingface_hub import AsyncInferenceClient

from utils.resilience import with_resilience

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")

_client = AsyncInferenceClient(token=HF_TOKEN)
_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@with_resilience()
async def get_embeddings(chunk: str) -> list[float]:
    raw = await _client.feature_extraction(
        chunk,
        model=_MODEL,
    )

    vector = np.array(raw, dtype=float)

    if vector.ndim > 1:
        vector = vector.mean(axis=0)

    norm = np.linalg.norm(vector)

    if norm == 0:
        raise ValueError("Embedding model returned a zero vector.")

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