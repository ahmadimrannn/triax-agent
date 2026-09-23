import asyncio
from functools import wraps


class ToolExecutionError(Exception):
    pass


def with_resilience(max_retries=3, backoff_base=1.5):
    def decorator(fn):

        @wraps(fn)
        async def wrapped(*args, **kwargs):
            last_err = None

            for attempt in range(max_retries):
                try:
                    return await fn(*args, **kwargs)

                except Exception as e:
                    last_err = e

                    if attempt < max_retries - 1:
                        delay = backoff_base ** attempt
                        await asyncio.sleep(delay)

            raise ToolExecutionError(
                f"{fn.__name__} failed after "
                f"{max_retries} attempts: {last_err}"
            ) from last_err

        return wrapped

    return decorator