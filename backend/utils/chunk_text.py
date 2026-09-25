import re

from dotenv import load_dotenv
from tokenizers import Tokenizer

load_dotenv()


tokenizer = Tokenizer.from_pretrained(
    "sentence-transformers/all-MiniLM-L6-v2"
)
tokenizer.no_truncation()


# Matches:
# 1. Refunds
# 1.1 Refund Policy
# # Refunds
# ## Refund Policy
SECTION_PATTERN = re.compile(
    r"(?m)^(?P<heading>"
    r"(?:\d+(?:\.\d+)*\.\s+.+)"
    r"|(?:#{1,6}\s+.+)"
    r")\s*$"
)


def split_sections(text: str) -> list[tuple[str, str]]:
    """
    Split a document into semantic sections using Markdown or
    numbered headings.

    Returns:
        [
            ("4. Refunds", "4. Refunds\n..."),
            ("4.1 Refund After Cancellation", "4.1 ..."),
            ...
        ]
    """

    matches = list(SECTION_PATTERN.finditer(text))

    if not matches:
        cleaned = text.strip()
        return [("", cleaned)] if cleaned else []

    sections = []

    # Content before the first heading.
    if matches[0].start() > 0:
        preamble = text[:matches[0].start()].strip()

        if preamble:
            sections.append(("", preamble))

    # Each heading becomes its own semantic section.
    for i, match in enumerate(matches):
        heading = match.group("heading").strip()

        start = match.start()

        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(text)

        section_text = text[start:end].strip()

        if section_text:
            sections.append((heading, section_text))

    return sections


def token_chunk(
    text: str,
    chunk_size: int = 180,
    chunk_overlap: int = 30,
) -> list[str]:
    """
    Split one semantic section into token-based chunks.

    Sections smaller than MIN_CHUNK_SIZE are preserved rather
    than discarded.
    """

    encoding = tokenizer.encode(
        text,
        add_special_tokens=False,
    )

    token_ids = encoding.ids

    if not token_ids:
        return []

    # Never discard a small but meaningful semantic section.
    if len(token_ids) <= chunk_size:
        return [text.strip()]

    offsets = encoding.offsets

    step = chunk_size - chunk_overlap

    if step <= 0:
        raise ValueError(
            "chunk_overlap must be smaller than chunk_size"
        )

    chunks = []

    start = 0

    while start < len(token_ids):
        end = min(
            start + chunk_size,
            len(token_ids),
        )

        char_start = offsets[start][0]
        char_end = offsets[end - 1][1]

        chunk = text[char_start:char_end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(token_ids):
            break

        start += step

    return chunks


def chunk_text(
    text: str,
    chunk_size: int = 180,
    chunk_overlap: int = 30,
) -> list[dict]:
    """
    Create retrieval-friendly chunks while preserving semantic
    section boundaries.

    Returns:
        [
            {
                "text": "...",
                "section": "4.1 Refund After Cancellation",
                "chunk_index": 0,
            },
            ...
        ]
    """

    text = text.strip()

    if not text:
        return []

    sections = split_sections(text)

    chunks = []

    for section_heading, section_text in sections:

        section_chunks = token_chunk(
            section_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        for chunk_index, chunk in enumerate(section_chunks):

            # Include the heading in the embedded text so the
            # embedding retains explicit topic context.
            if section_heading:
                embedding_text = (
                    f"Section: {section_heading}\n\n"
                    f"{chunk}"
                )
            else:
                embedding_text = chunk

            chunks.append(
                {
                    "text": embedding_text,
                    "section": section_heading,
                    "chunk_index": chunk_index,
                }
            )

    print(f"Total sections: {len(sections)}")
    print(f"Total chunks: {len(chunks)}")

    for i, chunk in enumerate(chunks, start=1):
        print(
            f"\nChunk {i}"
            f" | Section: {chunk['section']}"
            f" | Index: {chunk['chunk_index']}"
        )

        print(chunk["text"][:300])

    return chunks