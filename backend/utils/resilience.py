import asyncio
import logging
import random
from functools import wraps

logger = logging.getLogger(__name__)

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}
TRANSIENT_NAME_WORDS = ("timeout", "ratelimit", "connection", "overloaded", "unavailable", "exhausted", "deadline")


class ToolExecutionError(Exception):
    pass


def _status_of(err):
    for attr in ("status_code", "code"):
        value = getattr(err, attr, None)
        if isinstance(value, int):
            return value
    return getattr(getattr(err, "response", None), "status_code", None)


def _causes(err, limit=4):
    chain = []
    while err is not None and err not in chain and len(chain) < limit:
        chain.append(err)
        err = err.__cause__
    return chain


def is_transient(err):
    if isinstance(err, ToolExecutionError):
        return False
    for e in _causes(err):
        if isinstance(e, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
            return True
        if _status_of(e) in TRANSIENT_STATUS_CODES:
            return True
        name = type(e).__name__.lower()
        if any(word in name for word in TRANSIENT_NAME_WORDS):
            return True
    return False


def with_resilience(max_retries=3, base_delay=1.0, backoff_base=2.0, max_delay=20.0, timeout=60.0):
    def decorator(fn):

        @wraps(fn)
        async def wrapped(*args, **kwargs):
            last_err = None

            for attempt in range(max_retries):
                try:
                    return await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout)

                except Exception as e:
                    if not is_transient(e):
                        raise

                    last_err = e

                    if attempt < max_retries - 1:
                        delay = min(max_delay, base_delay * backoff_base ** attempt)
                        delay = delay * random.uniform(0.5, 1.5)
                        logger.warning(
                            "%s attempt %d/%d failed with %r. Retrying in %.1fs",
                            fn.__name__, attempt + 1, max_retries, e, delay,
                        )
                        await asyncio.sleep(delay)

            raise ToolExecutionError(
                f"{fn.__name__} failed after {max_retries} attempts: {last_err!r}"
            ) from last_err

        return wrapped

    return decorator