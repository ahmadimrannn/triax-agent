import re

from dotenv import load_dotenv
from tokenizers import Tokenizer
from config.settings import (
    GARBAGE_ONLY_PATTERN,
    NUMBERING_PATTERN,
)

load_dotenv()

tokenizer = Tokenizer.from_pretrained(
    "sentence-transformers/all-MiniLM-L6-v2"
)
tokenizer.no_truncation()


def is_meaningful_text(text: str) -> bool:
    if not text:
        return False

    cleaned = re.sub(r"\s+", " ", text).strip()

    if not cleaned:
        return False

    if GARBAGE_ONLY_PATTERN.fullmatch(cleaned):
        return False

    without_markers = NUMBERING_PATTERN.sub(" ", cleaned)

    words = re.findall(
        r"[A-Za-z]{2,}",
        without_markers,
    )

    return len(words) >= 3


def split_sections(text: str) -> list[tuple[str, str]]:
    """
    Split document into semantic sections.

    Valid headings:
        # Customer Support Policy
        ## Cancellation Policy
        1. Refunds
        1.1 Refund Eligibility
        1.2 Refund After Cancellation

    Invalid headings:
        1.
        2.
        3. 4.
        -
        *
        •
    """

    if not text or not text.strip():
        return []

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = text.splitlines()

    markdown_heading = re.compile(
        r"^\s*#{1,6}\s+(.+?)\s*$"
    )

    numbered_heading = re.compile(
        r"^\s*(\d+(?:\.\d+)*\.)\s+(.+?)\s*$"
    )

    garbage_line = re.compile(
        r"^\s*(?:\d+(?:\.\d+)*\.?|[-*•])\s*$"
    )

    def get_heading(line: str) -> str | None:
        line = line.strip()

        if not line:
            return None

        # Never treat standalone numbering/bullets as headings.
        if garbage_line.fullmatch(line):
            return None

        # Markdown heading.
        match = markdown_heading.fullmatch(line)

        if match:
            title = match.group(1).strip()

            # A markdown heading must contain actual letters.
            if re.search(r"[A-Za-z]{2,}", title):
                return line

            return None

        # Numbered heading.
        match = numbered_heading.fullmatch(line)

        if match:
            title = match.group(2).strip()

            # A numbered heading must contain actual words.
            if re.search(r"[A-Za-z]{2,}", title):
                return line

        return None

    # Find every real heading.
    heading_positions: list[tuple[int, str]] = []

    for index, line in enumerate(lines):
        heading = get_heading(line)

        if heading is not None:
            heading_positions.append(
                (index, heading)
            )

    if not heading_positions:
        cleaned_lines = []

        for line in lines:
            line = line.strip()

            if not line:
                continue

            if garbage_line.fullmatch(line):
                continue

            cleaned_lines.append(line)

        cleaned = "\n".join(
            cleaned_lines
        ).strip()

        if is_meaningful_text(cleaned):
            return [("", cleaned)]

        return []

    sections: list[tuple[str, str]] = []

    # Everything before the first heading is preamble.
    first_heading_index = heading_positions[0][0]

    if first_heading_index > 0:
        preamble_lines = []

        for line in lines[:first_heading_index]:
            line = line.strip()

            if not line:
                continue

            if garbage_line.fullmatch(line):
                continue

            preamble_lines.append(line)

        preamble = "\n".join(
            preamble_lines
        ).strip()

        if is_meaningful_text(preamble):
            sections.append(
                ("", preamble)
            )

    # Build each heading -> content section.
    for i, (start_index, heading) in enumerate(
        heading_positions
    ):

        if i + 1 < len(heading_positions):
            end_index = heading_positions[i + 1][0]
        else:
            end_index = len(lines)

        section_lines = []

        for line in lines[
            start_index + 1:end_index
        ]:
            line = line.strip()

            if not line:
                continue

            # Remove garbage-only lines.
            if garbage_line.fullmatch(line):
                continue

            section_lines.append(line)

        section_text = "\n".join(
            section_lines
        ).strip()

        if not section_text:
            continue

        # The heading itself can be short.
        # We only require the COMPLETE SECTION to
        # contain meaningful content.
        if not is_meaningful_text(section_text):
            continue

        sections.append(
            (
                heading,
                section_text,
            )
        )

    return sections

def token_chunk(
    text: str,
    chunk_size: int = 180,
    chunk_overlap: int = 30,
) -> list[str]:

    if not is_meaningful_text(text):
        return []

    if chunk_size <= 0:
        raise ValueError(
            "chunk_size must be greater than 0"
        )

    if chunk_overlap < 0:
        raise ValueError(
            "chunk_overlap cannot be negative"
        )

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be smaller than chunk_size"
        )

    encoding = tokenizer.encode(
        text,
        add_special_tokens=False,
    )

    token_ids = encoding.ids

    if not token_ids:
        return []

    if len(token_ids) <= chunk_size:
        return [text.strip()]

    offsets = encoding.offsets

    step = chunk_size - chunk_overlap

    chunks: list[str] = []

    start = 0

    while start < len(token_ids):

        end = min(
            start + chunk_size,
            len(token_ids),
        )

        char_start = offsets[start][0]
        char_end = offsets[end - 1][1]

        chunk = text[
            char_start:char_end
        ].strip()

        if is_meaningful_text(chunk):
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

    if not text or not text.strip():
        return []

    sections = split_sections(text)

    chunks: list[dict] = []

    for section_heading, section_text in sections:

        section_chunks = token_chunk(
            section_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        for chunk_index, chunk in enumerate(
            section_chunks
        ):

            if section_heading:
                embedding_text = (
                    f"Section: {section_heading}\n\n"
                    f"{chunk}"
                )
            else:
                embedding_text = chunk

            if not is_meaningful_text(
                embedding_text
            ):
                continue

            chunks.append(
                {
                    "text": embedding_text,
                    "section": section_heading,
                    "chunk_index": chunk_index,
                }
            )

    print(
        f"Total sections: {len(sections)}"
    )

    print(
        f"Total chunks: {len(chunks)}"
    )

    return chunks


if __name__ == "__main__":

    text = """
    # Customer Support Policy

    Welcome to our customer support knowledge base. This document explains refunds, account access, and subscription policies.

    1. Refunds

    Customers can request a refund within 30 days of the original purchase. Refund requests submitted after 30 days are normally not eligible.

    1.1 Refund Eligibility

    A customer is eligible for a refund if the product was purchased within the last 30 days and the customer has not violated the terms of service.

    1.2 Refund After Cancellation

    If a subscription is cancelled, the customer may request a refund for the unused portion of the billing period. Refunds are processed within 5 business days.

    1.3 Refund Exceptions

    Refunds are not available for purchases made more than 30 days ago. Promotional purchases may also have different refund conditions.

    2. Account Access
    Customers who cannot log in should first reset their password using the password reset page.

    2.1 Password Reset
    The password reset link is valid for 30 minutes. If the link expires, the customer must request a new reset link.

    2.2 Locked Accounts
    Accounts may be temporarily locked after multiple failed login attempts. The lock normally expires after 15 minutes.

    3. Subscription
    Customers can upgrade or downgrade their subscription from the billing settings page.

    ## Cancellation Policy

    Customers can cancel their subscription at any time. Cancellation prevents future charges but does not automatically issue a refund.

    4.

    1.

    2.

    -

    *

    •
    """

    chunks = chunk_text(text)

    print(
        "Length of chunks:",
        len(chunks),
    )

    for i, chunk in enumerate(
        chunks,
        start=1,
    ):
        print(
            f"\n--- Chunk {i} ---"
        )

        print(
            f"Section: {chunk['section']}"
        )

        print(
            f"Index: {chunk['chunk_index']}"
        )

        print(
            chunk["text"]
        )