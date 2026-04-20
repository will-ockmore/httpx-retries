import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import httpx
import pytest
from httpx import Request, Response

from httpx_retries import Retry, RetryTransport


def status_codes(
    codes: list[tuple[int, str | None]],
) -> Generator[tuple[int, str | None], None, None]:
    """Yields the given status codes, and then the last status code indefinitely."""
    yield from codes
    while True:
        yield codes[-1]


async def astatus_codes(
    codes: list[tuple[int, str | None]],
) -> AsyncGenerator[tuple[int, str | None], None]:
    """Yields the given status codes, and then the last status code indefinitely."""
    for code in codes:
        yield code

    while True:
        yield codes[-1]


def create_response(request: Request, status_code: int, retry_after: str | None = None) -> Response:
    """Helper to create a response with the given status code and retry-after header"""
    headers = {"Retry-After": retry_after} if retry_after else {}
    return Response(status_code=status_code, request=request, headers=headers)


StatusCodeTuple = tuple[int, str | None]
StatusCodeSequence = Generator[StatusCodeTuple, None, None]
AsyncStatusCodeSequence = AsyncGenerator[StatusCodeTuple, None]
MockResponse = tuple[MagicMock, dict[str, StatusCodeSequence | None]]
AsyncMockResponse = tuple[AsyncMock, dict[str, AsyncStatusCodeSequence | None]]


@pytest.fixture
def mock_responses(mock_sleep: MagicMock) -> Generator[MockResponse, None, None]:
    """Returns a mock for sleep and response sequences for sync requests"""
    status_code_sequences: dict[str, StatusCodeSequence | None] = {}

    def handle_request(request: Request) -> Response:
        if request.url in status_code_sequences:
            status_code_gen = status_code_sequences[str(request.url)]
            if status_code_gen is not None:
                status_code, retry_after = next(status_code_gen)
                return create_response(request, status_code, retry_after)
        return create_response(request, 200)

    with patch("httpx.HTTPTransport.handle_request") as mock_handle:
        mock_handle.side_effect = handle_request
        yield mock_sleep, status_code_sequences


@pytest.fixture
def mock_async_responses(
    mock_asleep: AsyncMock,
) -> Generator[AsyncMockResponse, None, None]:
    """Returns a mock for sleep and response sequences for async requests"""
    status_code_sequences: dict[str, AsyncStatusCodeSequence | None] = {}

    async def handle_async_request(request: Request) -> Response:
        if request.url in status_code_sequences:
            status_code_gen = status_code_sequences[str(request.url)]
            if status_code_gen is not None:
                status_code, retry_after = await status_code_gen.__anext__()
                return create_response(request, status_code, retry_after)
        return create_response(request, 200)

    with patch("httpx.AsyncHTTPTransport.handle_async_request") as mock_handle:
        mock_handle.side_effect = handle_async_request
        yield mock_asleep, status_code_sequences


class MockHTTPTransport(httpx.HTTPTransport):
    def handle_request(self, request: Request) -> Response:
        return create_response(request, 200)


class MockAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request: Request) -> Response:
        return create_response(request, 200)


class MockTransport(httpx.BaseTransport):
    def handle_request(self, request: Request) -> Response:
        return create_response(request, 200)


class MockAsyncTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: Request) -> Response:
        return create_response(request, 200)


def test_successful_request(mock_responses: MockResponse) -> None:
    mock_sleep, _ = mock_responses
    transport = RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com")

    assert response.status_code == 200
    assert mock_sleep.call_count == 0


def test_successful_request_logs(mock_responses: MockResponse, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    mock_sleep, _ = mock_responses
    transport = RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com")

    assert response.status_code == 200
    assert mock_sleep.call_count == 0
    assert "handle_request started request=<Request('GET', 'https://example.com')>" in caplog.text
    assert (
        "handle_request finished request=<Request('GET', 'https://example.com')> response=<Response [200 OK]>"
        in caplog.text
    )


def test_failed_request(mock_responses: MockResponse) -> None:
    mock_sleep, status_code_sequences = mock_responses
    status_code_sequences["https://example.com/fail"] = status_codes([(429, None)])
    transport = RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")

    assert response.status_code == 429
    assert mock_sleep.call_count == 10


def test_unretryable_status_code(mock_responses: MockResponse) -> None:
    mock_sleep, status_code_sequences = mock_responses
    status_code_sequences["https://example.com/fail"] = status_codes([(403, None), (200, None)])
    transport = RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")
        assert response.status_code == 403

    assert mock_sleep.call_count == 0


def test_unretryable_method(mock_responses: MockResponse) -> None:
    mock_sleep, status_code_sequences = mock_responses
    status_code_sequences["https://example.com/fail"] = status_codes([(429, None), (200, None)])
    transport = RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.post("https://example.com/fail")
        assert response.status_code == 429

    assert mock_sleep.call_count == 0


def test_non_standard_method_passes_through(mock_responses: MockResponse) -> None:
    mock_sleep, status_code_sequences = mock_responses
    status_code_sequences["https://example.com/dav"] = status_codes([(207, None)])
    transport = RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.request("PROPFIND", "https://example.com/dav")
        assert response.status_code == 207

    assert mock_sleep.call_count == 0


@pytest.mark.asyncio
async def test_async_non_standard_method_passes_through(
    mock_async_responses: AsyncMockResponse,
) -> None:
    mock_asleep, status_code_sequences = mock_async_responses
    status_code_sequences["https://example.com/dav"] = astatus_codes([(207, None)])
    transport = RetryTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.request("PROPFIND", "https://example.com/dav")
        assert response.status_code == 207

    assert mock_asleep.call_count == 0


def test_unretryable_exception(mock_responses: MockResponse) -> None:
    mock_sleep, _ = mock_responses
    transport = RetryTransport()

    with patch(
        "httpx.HTTPTransport.handle_request",
        side_effect=httpx.ProxyError("Proxy error"),
    ):
        with httpx.Client(transport=transport) as client:
            with pytest.raises(httpx.ProxyError, match="Proxy error"):
                client.get("https://example.com")

    assert mock_sleep.call_count == 0


@pytest.mark.asyncio
async def test_async_unretryable_exception(
    mock_async_responses: AsyncMockResponse,
) -> None:
    mock_asleep, _ = mock_async_responses
    transport = RetryTransport()

    with patch(
        "httpx.AsyncHTTPTransport.handle_async_request",
        side_effect=httpx.ProxyError("Proxy error"),
    ):
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(httpx.ProxyError, match="Proxy error"):
                await client.get("https://example.com")

    assert mock_asleep.call_count == 0


def test_retryable_exception(mock_responses: MockResponse) -> None:
    mock_sleep, _ = mock_responses
    transport = RetryTransport()

    with patch("httpx.HTTPTransport.handle_request", side_effect=httpx.ReadTimeout("Timeout!")):
        with httpx.Client(transport=transport) as client:
            with pytest.raises(httpx.ReadTimeout, match="Timeout!"):
                client.get("https://example.com")

    assert mock_sleep.call_count == 10


def test_retryable_exception_custom_exception(mock_responses: MockResponse) -> None:
    mock_sleep, _ = mock_responses
    transport = RetryTransport(retry=Retry(retry_on_exceptions=[ValueError]))

    with patch("httpx.HTTPTransport.handle_request", side_effect=ValueError("oops")):
        with httpx.Client(transport=transport) as client:
            with pytest.raises(ValueError, match="oops"):
                client.get("https://example.com")

    assert mock_sleep.call_count == 10


@pytest.mark.parametrize("status_code", Retry.RETRYABLE_STATUS_CODES)
def test_retry_operation_always_closes_response(status_code: int) -> None:
    transport = RetryTransport()

    responses = []

    def send_method(request: httpx.Request) -> httpx.Response:
        response = Mock(spec=httpx.Response)
        response.status_code = status_code
        response.headers = httpx.Headers()
        response.close = Mock()

        responses.append(response)
        return response

    transport._retry_operation(request=httpx.Request("GET", "https://example.com"), send_method=send_method)

    assert all(r.close.called for r in responses[:-1])


@pytest.mark.asyncio
async def test_async_retryable_exception(
    mock_async_responses: AsyncMockResponse,
) -> None:
    mock_asleep, _ = mock_async_responses
    transport = RetryTransport()

    with patch(
        "httpx.AsyncHTTPTransport.handle_async_request",
        side_effect=httpx.ReadTimeout("oops"),
    ):
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(httpx.ReadTimeout, match="oops"):
                await client.get("https://example.com")

    assert mock_asleep.call_count == 10


@pytest.mark.asyncio
async def test_async_retryable_exception_custom_exception(
    mock_async_responses: AsyncMockResponse,
) -> None:
    mock_asleep, _ = mock_async_responses
    transport = RetryTransport(retry=Retry(retry_on_exceptions=[ValueError]))

    with patch(
        "httpx.AsyncHTTPTransport.handle_async_request",
        side_effect=ValueError("Timeout!"),
    ):
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(ValueError, match="Timeout!"):
                await client.get("https://example.com")

    assert mock_asleep.call_count == 10


@pytest.mark.asyncio
async def test_successful_async_request_logs(
    mock_async_responses: AsyncMockResponse, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    mock_asleep, _ = mock_async_responses
    transport = RetryTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com")

    assert response.status_code == 200
    assert mock_asleep.call_count == 0
    assert "handle_async_request started request=<Request('GET', 'https://example.com')>" in caplog.text
    assert (
        "handle_async_request finished request=<Request('GET', 'https://example.com')> response=<Response [200 OK]>"
        in caplog.text
    )


def test_custom_retryable_exception(mock_responses: MockResponse) -> None:
    mock_sleep, _ = mock_responses

    retry = Retry(retry_on_exceptions=[httpx.ProxyError])
    transport = RetryTransport(retry=retry)

    with patch(
        "httpx.HTTPTransport.handle_request",
        side_effect=httpx.ProxyError("Proxy error"),
    ):
        with httpx.Client(transport=transport) as client:
            with pytest.raises(httpx.ProxyError, match="Proxy error"):
                client.get("https://example.com")

    assert mock_sleep.call_count == 10

    # Verify other exceptions are not retried
    transport = RetryTransport(retry=retry)
    with patch("httpx.HTTPTransport.handle_request", side_effect=httpx.ReadTimeout("Timeout!")):
        with httpx.Client(transport=transport) as client:
            with pytest.raises(httpx.ReadTimeout, match="Timeout!"):
                client.get("https://example.com")

    assert mock_sleep.call_count == 10  # Count shouldn't increase


def test_retries_reset_for_new_request(mock_responses: MockResponse) -> None:
    mock_sleep, status_code_sequences = mock_responses
    status_code_sequences["https://example.com/fail"] = status_codes([(429, None)])
    status_code_sequences["https://example.com/fail2"] = status_codes([(429, None)])
    transport = RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")
        assert response.status_code == 429

        response = client.get("https://example.com/fail2")
        assert response.status_code == 429

    assert mock_sleep.call_count == 20


def test_retry_respects_retry_after_header(mock_responses: MockResponse) -> None:
    mock_sleep, status_code_sequences = mock_responses
    status_code_sequences["https://example.com/fail"] = status_codes([(429, "5")])
    transport = RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")
        assert response.status_code == 429

    assert mock_sleep.call_count == 10
    mock_sleep.assert_has_calls([call(5)] * 10)


def test_transport_logs_retry_operation(mock_responses: MockResponse, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    mock_sleep, status_code_sequences = mock_responses
    status_code_sequences["https://example.com/fail"] = status_codes([(429, "5")])
    transport = RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")
        assert response.status_code == 429

    records = [r for r in caplog.records if r.message.startswith("_retry_operation")]

    assert len(records) == 10
    assert records[0].message == (
        "_retry_operation retrying request=<Request('GET', 'https://example.com/fail')> "
        "response=<Response [429 Too Many Requests]> retry=<Retry(total=10, attempts_made=0)>"
    )
    assert records[-1].message == (
        "_retry_operation retrying request=<Request('GET', 'https://example.com/fail')> "
        "response=<Response [429 Too Many Requests]> retry=<Retry(total=10, attempts_made=9)>"
    )


@pytest.mark.asyncio
async def test_async_retry_operation_logs(
    mock_async_responses: AsyncMockResponse, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    mock_asleep, status_code_sequences = mock_async_responses
    status_code_sequences["https://example.com/fail"] = astatus_codes([(429, "5")])
    transport = RetryTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com/fail")
        assert response.status_code == 429

    records = [r for r in caplog.records if r.message.startswith("_retry_operation_async")]
    assert len(records) == 10
    assert records[0].message == (
        "_retry_operation_async retrying request=<Request('GET', 'https://example.com/fail')> "
        "response=<Response [429 Too Many Requests]> retry=<Retry(total=10, attempts_made=0)>"
    )
    assert records[-1].message == (
        "_retry_operation_async retrying request=<Request('GET', 'https://example.com/fail')> "
        "response=<Response [429 Too Many Requests]> retry=<Retry(total=10, attempts_made=9)>"
    )


@pytest.mark.asyncio
async def test_async_successful_request(
    mock_async_responses: AsyncMockResponse,
) -> None:
    mock_asleep, status_code_sequences = mock_async_responses
    transport = RetryTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com")

    assert response.status_code == 200
    assert mock_asleep.call_count == 0


@pytest.mark.asyncio
async def test_async_failed_request(mock_async_responses: AsyncMockResponse) -> None:
    mock_asleep, status_code_sequences = mock_async_responses
    status_code_sequences["https://example.com/fail"] = astatus_codes([(429, None)])
    transport = RetryTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com/fail")

    assert response.status_code == 429
    assert mock_asleep.call_count == 10


@pytest.mark.asyncio
async def test_sync_only_transport() -> None:
    transport = RetryTransport(transport=MockHTTPTransport())

    # Sync works
    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com")
        assert response.status_code == 200

    # Async fails
    with pytest.raises(RuntimeError, match="Async request received but no async transport available"):
        async with httpx.AsyncClient(transport=transport) as client:
            await client.get("https://example.com")


@pytest.mark.asyncio
async def test_async_only_transport() -> None:
    transport = RetryTransport(transport=MockAsyncHTTPTransport())

    # Async works
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com")
        assert response.status_code == 200

    # Sync fails
    with pytest.raises(
        RuntimeError,
        match="Synchronous request received but no sync transport available",
    ):
        with httpx.Client(transport=transport) as client:
            client.get("https://example.com")


@pytest.mark.asyncio
async def test_async_unretryable_method(
    mock_async_responses: AsyncMockResponse,
) -> None:
    mock_asleep, status_code_sequences = mock_async_responses
    status_code_sequences["https://example.com/fail"] = astatus_codes([(429, None), (200, None)])
    transport = RetryTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.post("https://example.com/fail")
        assert response.status_code == 429

    assert mock_asleep.call_count == 0


@pytest.mark.asyncio
async def test_sync_from_base_transport() -> None:
    transport = RetryTransport(transport=MockTransport())

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_async_from_base_transport() -> None:
    transport = RetryTransport(transport=MockAsyncTransport())

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com")
        assert response.status_code == 200


def test_retry_after_capped_by_total_timeout(mock_responses: MockResponse) -> None:
    mock_sleep, status_code_sequences = mock_responses
    status_code_sequences["https://example.com/fail"] = status_codes([(429, "120")])
    retry = Retry(total=10, total_timeout=10)
    transport = RetryTransport(retry=retry)

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")

    assert response.status_code == 429
    total_slept = sum(c.args[0] for c in mock_sleep.call_args_list)
    assert total_slept <= 10
    assert mock_sleep.call_count < 10


@pytest.mark.asyncio
async def test_async_retry_after_capped_by_total_timeout(
    mock_async_responses: AsyncMockResponse,
) -> None:
    mock_asleep, status_code_sequences = mock_async_responses
    status_code_sequences["https://example.com/fail"] = astatus_codes([(429, "120")])
    retry = Retry(total=10, total_timeout=10)
    transport = RetryTransport(retry=retry)

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com/fail")

    assert response.status_code == 429
    total_slept = sum(c.args[0] for c in mock_asleep.call_args_list)
    assert total_slept <= 10
    assert mock_asleep.call_count < 10


@pytest.mark.parametrize("status_code", Retry.RETRYABLE_STATUS_CODES)
@pytest.mark.asyncio
async def test_retry_operation_async_always_closes_response(status_code: int) -> None:
    transport = RetryTransport()

    responses = []

    async def send_method(request: httpx.Request) -> httpx.Response:
        response = AsyncMock(spec=httpx.Response)
        response.status_code = status_code
        response.headers = httpx.Headers()
        response.aclose = AsyncMock()

        responses.append(response)
        return response

    await transport._retry_operation_async(request=httpx.Request("GET", "https://example.com"), send_method=send_method)

    assert all(r.aclose.called for r in responses[:-1])


# a retry backoff on one coroutine must not block peer coroutines sharing the
# event loop. These tests intentionally avoid the mock_asleep fixture because
# mocking asyncio.sleep short-circuits the scheduler and defeats the check.


@pytest.mark.asyncio
async def test_async_retry_does_not_block_peer_coroutine() -> None:
    slow_calls = 0

    async def handle_request(request: Request) -> Response:
        nonlocal slow_calls
        if str(request.url) == "https://example.com/slow":
            slow_calls += 1
            if slow_calls == 1:
                return create_response(request, 503)
        return create_response(request, 200)

    with patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=handle_request):
        retry = Retry(total=3, backoff_factor=0.2, backoff_jitter=0.0)
        transport = RetryTransport(retry=retry)

        async with httpx.AsyncClient(transport=transport) as client:
            slow_task = asyncio.create_task(client.get("https://example.com/slow"))

            # Let slow reach its first 503 and enter asyncio.sleep before we race.
            await asyncio.sleep(0.05)

            fast_start = time.monotonic()
            fast_response = await client.get("https://example.com/fast")
            fast_elapsed = time.monotonic() - fast_start

            slow_response = await slow_task

        assert fast_response.status_code == 200
        assert slow_response.status_code == 200
        # Backoff for attempts_made=1 is 0.2 * 2 = 0.4s; fast must not be serialised behind it.
        assert fast_elapsed < 0.2, f"fast request took {fast_elapsed:.3f}s — retry appears to block peers"


@pytest.mark.asyncio
async def test_async_concurrent_retries_do_not_serialize() -> None:
    call_counts: dict[str, int] = {}

    async def handle_request(request: Request) -> Response:
        url = str(request.url)
        call_counts[url] = call_counts.get(url, 0) + 1
        if call_counts[url] == 1:
            return create_response(request, 503)
        return create_response(request, 200)

    with patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=handle_request):
        retry = Retry(total=2, backoff_factor=0.15, backoff_jitter=0.0)
        transport = RetryTransport(retry=retry)

        async with httpx.AsyncClient(transport=transport) as client:
            start = time.monotonic()
            responses = await asyncio.gather(
                client.get("https://example.com/a"),
                client.get("https://example.com/b"),
                client.get("https://example.com/c"),
            )
            elapsed = time.monotonic() - start

        assert [r.status_code for r in responses] == [200, 200, 200]
        # Each request sleeps 0.3s once. Parallel ≈ 0.3s; serialised ≈ 0.9s.
        assert elapsed < 0.7, f"three concurrent retries took {elapsed:.3f}s — they look serialised"


@pytest.mark.asyncio
async def test_async_retry_sleep_yields_to_event_loop() -> None:
    async def handle_request(request: Request) -> Response:
        if str(request.url) == "https://example.com/retry":
            if handle_request.calls == 0:  # type: ignore[attr-defined]
                handle_request.calls += 1  # type: ignore[attr-defined]
                return create_response(request, 503)
        return create_response(request, 200)

    handle_request.calls = 0  # type: ignore[attr-defined]

    counter = 0
    stop = asyncio.Event()

    async def ticker() -> None:
        nonlocal counter
        while not stop.is_set():
            await asyncio.sleep(0.01)
            counter += 1

    with patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=handle_request):
        retry = Retry(total=3, backoff_factor=0.2, backoff_jitter=0.0)
        transport = RetryTransport(retry=retry)

        async with httpx.AsyncClient(transport=transport) as client:
            ticker_task = asyncio.create_task(ticker())
            response = await client.get("https://example.com/retry")
            stop.set()
            await ticker_task

    assert response.status_code == 200
    # Retry sleep is 0.4s. A non-blocked loop should tick ~40 times at 10ms cadence;
    # a blocked loop would tick 0 or 1 times.
    assert counter > 5, f"ticker only advanced {counter} times during retry — event loop looks blocked"


@pytest.mark.asyncio
async def test_async_shared_transport_isolates_retry_state() -> None:
    call_counts: dict[str, int] = {}

    async def handle_request(request: Request) -> Response:
        url = str(request.url)
        call_counts[url] = call_counts.get(url, 0) + 1
        if call_counts[url] <= 2:
            return create_response(request, 503)
        return create_response(request, 200)

    with patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=handle_request):
        retry = Retry(total=3, total_timeout=10.0, backoff_factor=0.05, backoff_jitter=0.0)
        transport = RetryTransport(retry=retry)

        async with httpx.AsyncClient(transport=transport) as client:
            responses = await asyncio.gather(
                client.get("https://example.com/x"),
                client.get("https://example.com/y"),
            )

        assert [r.status_code for r in responses] == [200, 200]
        # The transport's seed Retry must remain pristine — concurrent requests
        # must not mutate it, or retry budgets leak across requests.
        assert transport.retry.attempts_made == 0
        assert transport.retry.elapsed_sleep == 0.0
