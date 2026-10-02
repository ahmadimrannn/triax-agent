import asyncio

from utils import resilience
from utils.resilience import ToolExecutionError, is_transient, with_resilience


class FakeHTTPError(Exception):
    def __init__(self, status_code):
        super().__init__(f"http {status_code}")
        self.status_code = status_code


class RateLimitError(Exception):
    pass


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class WrappedResponseError(Exception):
    def __init__(self, status_code):
        super().__init__("wrapped")
        self.response = FakeResponse(status_code)


def run(coro_fn):
    delays = []
    original_sleep = asyncio.sleep

    async def fake_sleep(delay, *args, **kwargs):
        delays.append(delay)

    asyncio.sleep = fake_sleep
    try:
        try:
            return ("ok", asyncio.run(coro_fn())), delays
        except Exception as e:
            return ("error", e), delays
    finally:
        asyncio.sleep = original_sleep


def test_transient_failures_then_success_is_retried():
    calls = []

    @with_resilience(max_retries=3)
    async def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise FakeHTTPError(429)
        return "done"

    (kind, value), delays = run(flaky)
    assert kind == "ok" and value == "done"
    assert len(calls) == 3
    assert len(delays) == 2


def test_permanent_error_is_raised_at_once_with_its_own_type():
    calls = []

    @with_resilience(max_retries=3)
    async def broken():
        calls.append(1)
        raise ValueError("bad input")

    (kind, value), delays = run(broken)
    assert kind == "error"
    assert type(value) is ValueError
    assert len(calls) == 1
    assert delays == []


def test_400_is_not_retried_but_503_is():
    calls_400, calls_503 = [], []

    @with_resilience(max_retries=3)
    async def bad_request():
        calls_400.append(1)
        raise FakeHTTPError(400)

    @with_resilience(max_retries=3)
    async def unavailable():
        calls_503.append(1)
        raise FakeHTTPError(503)

    (kind, value), _ = run(bad_request)
    assert type(value) is FakeHTTPError and len(calls_400) == 1
    (kind, value), _ = run(unavailable)
    assert type(value) is ToolExecutionError and len(calls_503) == 3


def test_always_failing_transient_raises_tool_execution_error_after_max_retries():
    calls = []

    @with_resilience(max_retries=3)
    async def always_down():
        calls.append(1)
        raise FakeHTTPError(500)

    (kind, value), delays = run(always_down)
    assert type(value) is ToolExecutionError
    assert isinstance(value.__cause__, FakeHTTPError)
    assert "always_down failed after 3 attempts" in str(value)
    assert len(calls) == 3
    assert len(delays) == 2


def test_a_hanging_call_times_out_and_is_retried():
    calls = []

    @with_resilience(max_retries=2, timeout=0.05)
    async def hangs():
        calls.append(1)
        await asyncio.Event().wait()

    (kind, value), delays = run(hangs)
    assert type(value) is ToolExecutionError
    assert len(calls) == 2
    assert len(delays) == 1


def test_backoff_grows_and_has_jitter_within_bounds():
    @with_resilience(max_retries=4, base_delay=1.0, backoff_base=2.0, max_delay=20.0)
    async def always_down():
        raise FakeHTTPError(502)

    (_, _), delays = run(always_down)
    assert len(delays) == 3
    for attempt, delay in enumerate(delays):
        expected = 1.0 * 2.0 ** attempt
        assert 0.5 * expected <= delay <= 1.5 * expected


def test_delay_is_capped():
    @with_resilience(max_retries=4, base_delay=10.0, backoff_base=10.0, max_delay=15.0)
    async def always_down():
        raise FakeHTTPError(502)

    (_, _), delays = run(always_down)
    assert all(d <= 15.0 * 1.5 for d in delays)


def test_permanent_error_after_a_transient_one_keeps_its_type():
    calls = []

    @with_resilience(max_retries=3)
    async def mixed():
        calls.append(1)
        if len(calls) == 1:
            raise FakeHTTPError(429)
        raise ValueError("now it is a real bug")

    (kind, value), delays = run(mixed)
    assert type(value) is ValueError
    assert len(calls) == 2
    assert len(delays) == 1


def test_arguments_and_name_are_preserved():
    @with_resilience()
    async def add(a, b, extra=0):
        return a + b + extra

    (kind, value), _ = run(lambda: add(1, 2, extra=3))
    assert value == 6
    assert add.__name__ == "add"


def test_is_transient_classification():
    assert is_transient(TimeoutError())
    assert is_transient(asyncio.TimeoutError())
    assert is_transient(ConnectionError())
    assert is_transient(FakeHTTPError(429))
    assert is_transient(FakeHTTPError(503))
    assert is_transient(RateLimitError())
    assert is_transient(WrappedResponseError(502))
    assert not is_transient(ValueError())
    assert not is_transient(KeyError("x"))
    assert not is_transient(FakeHTTPError(400))
    assert not is_transient(FakeHTTPError(404))
    assert not is_transient(WrappedResponseError(422))


class CodeOnlyError(Exception):
    def __init__(self, code):
        super().__init__(f"code {code}")
        self.code = code


class WrapperError(Exception):
    pass


def test_errors_that_carry_code_instead_of_status_code_are_recognised():
    assert is_transient(CodeOnlyError(429))
    assert is_transient(CodeOnlyError(500))
    assert is_transient(CodeOnlyError(504))
    assert not is_transient(CodeOnlyError(400))
    bad = Exception("x")
    bad.code = "429"
    assert not is_transient(bad)


def test_wrapped_error_is_judged_by_its_explicit_cause():
    try:
        try:
            raise CodeOnlyError(503)
        except CodeOnlyError as inner:
            raise WrapperError("wrapped") from inner
    except WrapperError as wrapped:
        assert is_transient(wrapped)


def test_error_raised_while_handling_a_timeout_is_not_treated_as_transient():
    try:
        try:
            raise TimeoutError()
        except TimeoutError:
            raise ValueError("a real bug that happened during cleanup")
    except ValueError as err:
        assert not is_transient(err)


def test_nested_tool_execution_error_is_not_retried_again():
    calls = []

    @with_resilience(max_retries=3)
    async def outer():
        calls.append(1)
        raise ToolExecutionError("inner call already retried")

    (kind, value), delays = run(outer)
    assert type(value) is ToolExecutionError
    assert len(calls) == 1
    assert delays == []


def test_exhausted_and_deadline_names_are_transient():
    class ResourceExhausted(Exception):
        pass

    class DeadlineExceeded(Exception):
        pass

    assert is_transient(ResourceExhausted())
    assert is_transient(DeadlineExceeded())


def test_real_google_errors_if_installed():
    try:
        from google.api_core import exceptions as g
    except ImportError:
        return
    for cls in (g.ResourceExhausted, g.ServiceUnavailable, g.DeadlineExceeded, g.InternalServerError):
        assert is_transient(cls("x")), cls.__name__
    for cls in (g.InvalidArgument, g.NotFound, g.PermissionDenied):
        assert not is_transient(cls("x")), cls.__name__
    try:
        from google.genai import errors
    except ImportError:
        return
    body = {"error": {"message": "m", "status": "S"}}
    assert is_transient(errors.ClientError(429, body))
    assert is_transient(errors.ServerError(503, body))
    assert not is_transient(errors.ClientError(400, body))


if __name__ == "__main__":
    import sys

    all_tests = [(name, fn) for name, fn in list(globals().items()) if name.startswith("test_") and callable(fn)]
    failures = 0
    for name, fn in all_tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:
            failures += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(all_tests) - failures} passed, {failures} failed")
    sys.exit(1 if failures else 0)