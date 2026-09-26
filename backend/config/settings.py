import re

LLM_MODEL_NAME="gemini-3.5-flash-lite"
MIN_CHUNK_SIZE = 50

URGENCY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}

TOP_K = 5
MAX_DISTANCE = 0.7

# Obvious PDF extraction artifacts:
GARBAGE_ONLY_PATTERN = re.compile(
    r"^(?:"
    r"[\d\s.,:;|]+"
    r"|[-*•\s]+"
    r"|(?:[\d\s.,:;|]+[-*•\s]*)+"
    r")$"
)

# Common PDF numbering artifacts that can appear inside
# otherwise broken extracted text.
NUMBERING_PATTERN = re.compile(
    r"(?:^|\s)"
    r"(?:\d+(?:\.\d+)*\.?|[-*•])"
    r"(?=\s|$)"
)