import os
import numpy as np
from huggingface_hub import InferenceClient
from utils.resilience import with_resilience
from dotenv import load_dotenv

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")

_client = InferenceClient(token=HF_TOKEN)
_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

@with_resilience()
def get_embeddings(chunk: str) -> list[float]:
    try:
        raw = _client.feature_extraction(chunk, model=_MODEL)
        vector = np.array(raw, dtype=float)

        if vector.ndim > 1:
            vector = vector.mean(axis=0)

        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector.tolist()
    except Exception as e:
        return []


if __name__ == "__main__":
    chunk = "my name is ahmad"

    embeddings = get_embeddings(chunk)
    print("Length of embeddings:", {len(embeddings)})
    print(embeddings)

