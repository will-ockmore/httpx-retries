import logging
from collections.abc import AsyncGenerator, Generator
from typing import Dict, Optional, Union
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest
from httpx import Request, Response

from httpx_retries import Retry, RetryTransport


def status_codes(codes: list[tuple[int, Union[str, None]]]) -> Generator[tuple[int, Union[str, None]], None, None]:
    """Yields the given status codes, and then the last status code indefinitely."""
    yield from codes
    while True:
        yield codes[-1]


async def astatus_codes(
    codes: list[tuple[int, Union[str, None]]],
) -> AsyncGenerator[tuple[int, Union[str, None]], None]:
    """Yields the given status codes, and then the last status code indefinitely."""
    for code in codes:
        yield code

    while True:
        yield codes[-1]


def create_response(request: Request, status_code: int, retry_after: Optional[str] = None) -> Response:
    """Helper to create a response with the given status code and retry-after header"""
    headers = {"Retry-After": retry_after} if retry_after else {}
    return Response(status_code=status_code, request=request, headers=headers)


StatusCodeTuple = tuple[int, Union[str, None]]
StatusCodeSequence = Generator[StatusCodeTuple, None, None]
AsyncStatusCodeSequence = AsyncGenerator[StatusCodeTuple, None]
MockResponse = tuple[MagicMock, Dict[str, Optional[StatusCodeSequence]]]
AsyncMockResponse = tuple[AsyncMock, Dict[str, Optional[AsyncStatusCodeSequence]]]


@pytest.fixture
def mock_responses(mock_sleep: MagicMock) -> Generator[MockResponse, None, None]:
    """Returns a mock for sleep and response sequences for sync requests"""
    status_code_sequences: Dict[str, Optional[StatusCodeSequence]] = {}

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
def mock_async_responses(mock_asleep: AsyncMock) -> Generator[AsyncMockResponse, None, None]:
    """Returns a mock for sleep and response sequences for async requests"""
    status_code_sequences: Dict[str, Optional[AsyncStatusCodeSequence]] = {}

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


def test_unretryable_exception(mock_responses: MockResponse) -> None:
    mock_sleep, _ = mock_responses
    transport = RetryTransport()

    with patch("httpx.HTTPTransport.handle_request", side_effect=httpx.ProxyError("Proxy error")):
        with httpx.Client(transport=transport) as client:
            with pytest.raises(httpx.ProxyError, match="Proxy error"):
                client.get("https://example.com")

    assert mock_sleep.call_count == 0


@pytest.mark.asyncio
async def test_async_unretryable_exception(mock_async_responses: AsyncMockResponse) -> None:
    mock_asleep, _ = mock_async_responses
    transport = RetryTransport()

    with patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=httpx.ProxyError("Proxy error")):
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


@pytest.mark.asyncio
async def test_async_retryable_exception(mock_async_responses: AsyncMockResponse) -> None:
    mock_asleep, _ = mock_async_responses
    transport = RetryTransport()

    with patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=httpx.ReadTimeout("Timeout!")):
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(httpx.ReadTimeout, match="Timeout!"):
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

    with patch("httpx.HTTPTransport.handle_request", side_effect=httpx.ProxyError("Proxy error")):
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
async def test_async_successful_request(mock_async_responses: AsyncMockResponse) -> None:
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
    with pytest.raises(RuntimeError, match="Synchronous request received but no sync transport available"):
        with httpx.Client(transport=transport) as client:
            client.get("https://example.com")


@pytest.mark.asyncio
async def test_async_unretryable_method(mock_async_responses: AsyncMockResponse) -> None:
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
