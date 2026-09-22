import time
from functools import wraps

class ToolExecutionError(Exception):
    pass

def with_resilience(max_retries=3, backoff_base=1.5):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            last_err = None
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    if attempt < max_retries - 1:
                        time.sleep(backoff_base ** attempt)
            raise ToolExecutionError(f"{fn.__name__} failed after {max_retries} attempts: {last_err}")
        return wrapped
    return decorator