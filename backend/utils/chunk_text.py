from tokenizers import Tokenizer
from dotenv import load_dotenv
from config.settings import MIN_CHUNK_SIZE
from utils.resilience import with_resilience

load_dotenv()

tokenizer = Tokenizer.from_pretrained(
    "sentence-transformers/all-MiniLM-L6-v2"
)
tokenizer.no_truncation()

@with_resilience
def chunk_text(text: str, chunk_size: int = 200, chunk_overlap: int = 40):
    encoding = tokenizer.encode(text, add_special_tokens=False)
    token_ids = encoding.ids

    print("Total tokens:", len(token_ids))
    if len(token_ids) < MIN_CHUNK_SIZE:
        return []

    
    offsets = encoding.offsets

    # First pass: just work out (start, end) token index pairs.
    # No text slicing yet, so merging later is just adjusting numbers,
    # not stitching strings back together.
    boundaries = []
    start = 0
    while start < len(token_ids):
        end = min(start + chunk_size, len(token_ids))
        boundaries.append((start, end))
        start += chunk_size - chunk_overlap

    # If the last chunk is too small, and there's a previous chunk to
    # merge it into, extend the previous chunk's end to cover it,
    # then drop the last one from the list.
    if len(boundaries) > 1:
        last_start, last_end = boundaries[-1]
        if (last_end - last_start) < MIN_CHUNK_SIZE:
            prev_start, _ = boundaries[-2]
            boundaries[-2] = (prev_start, last_end)
            boundaries.pop()

    # Second pass: now build the real text for each finalized boundary,
    # using character offsets from the original string.
    chunks = []
    for i, (start, end) in enumerate(boundaries):
        char_start = offsets[start][0]
        char_end = offsets[end - 1][1]
        chunk = text[char_start:char_end]
        chunks.append(chunk)
        print(f"Chunk {i + 1}: tokens {start}:{end}")

    return chunks

if __name__ == "__main__":
    text = """Renewable energy has moved from a niche environmental concern to a central pillar of global economic strategy over the past two decades. Solar panel costs have fallen by more than ninety percent since 2010, driven"""

    chunks = chunk_text(text)
    print("Chunks:", chunks)