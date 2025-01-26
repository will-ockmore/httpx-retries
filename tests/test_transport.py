from collections.abc import AsyncGenerator, Generator
from typing import Optional, Union
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest
from httpx import Request, Response

import httpx_retries


def status_codes(codes: list[tuple[int, Union[str, None]]]) -> Generator[tuple[int, Union[str, None]], None, None]:
    """
    Yields the given status codes, and then the last status code indefinitely.
    """
    yield from codes
    while True:
        yield codes[-1]


async def astatus_codes(
    codes: list[tuple[int, Union[str, None]]],
) -> AsyncGenerator[tuple[int, Union[str, None]], None]:
    """
    Yields the given status codes, and then the last status code indefinitely.
    """
    for code in codes:
        yield code

    while True:
        yield codes[-1]


def create_response(request: Request, status_code: int, retry_after: Optional[str] = None) -> Response:
    """Helper to create a response with the given status code and retry-after header"""
    headers = {"Retry-After": retry_after} if retry_after else {}
    return Response(status_code=status_code, request=request, headers=headers)


@pytest.fixture
def mock_transport(mock_sleep: MagicMock) -> Generator[tuple[MagicMock, dict], None, None]:
    """
    Returns a mock for sleep and a dict to store status code sequences.
    The mock will return responses based on the status_code_sequences.
    """
    status_code_sequences = {}

    def handle_request(request: Request) -> Response:
        # Get the generator for the URL if it exists
        if request.url in status_code_sequences:
            status_code_gen = status_code_sequences[request.url]
            if status_code_gen is not None:
                status_code, retry_after = next(status_code_gen)
                return create_response(request, status_code, retry_after)

        return create_response(request, 200)

    with patch("httpx.HTTPTransport.handle_request") as mock_handle:
        mock_handle.side_effect = handle_request
        yield mock_sleep, status_code_sequences


@pytest.fixture
def mock_async_transport(mock_asleep: AsyncMock) -> Generator[tuple[AsyncMock, dict], None, None]:
    """
    Returns a mock for async sleep and a dict to store status code sequences.
    The mock will return responses based on the status_code_sequences.
    """
    status_code_sequences = {}

    async def handle_async_request(request: Request) -> Response:
        # Get the generator for the URL if it exists
        if request.url in status_code_sequences:
            status_code_gen = status_code_sequences[request.url]
            if status_code_gen is not None:
                status_code, retry_after = await status_code_gen.__anext__()
                return create_response(request, status_code, retry_after)

        return create_response(request, 200)

    with patch("httpx.AsyncHTTPTransport.handle_async_request") as mock_handle:
        mock_handle.side_effect = handle_async_request
        yield mock_asleep, status_code_sequences


def test_successful_request(mock_transport: tuple[MagicMock, dict]) -> None:
    mock_sleep, _ = mock_transport
    transport = httpx_retries.RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com")

    assert response.status_code == 200
    assert mock_sleep.call_count == 0


def test_failed_request(mock_transport: tuple[MagicMock, dict]) -> None:
    mock_sleep, status_code_sequences = mock_transport
    status_code_sequences["https://example.com/fail"] = status_codes([(429, None)])
    transport = httpx_retries.RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")

    assert response.status_code == 429
    assert mock_sleep.call_count == 10


def test_unretryable_status_code(mock_transport: tuple[MagicMock, dict]) -> None:
    mock_sleep, status_code_sequences = mock_transport
    status_code_sequences["https://example.com/fail"] = status_codes([(403, None), (200, None)])
    transport = httpx_retries.RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")
        assert response.status_code == 403

    assert mock_sleep.call_count == 0


def test_unretryable_method(mock_transport: tuple[MagicMock, dict]) -> None:
    mock_sleep, status_code_sequences = mock_transport
    status_code_sequences["https://example.com/fail"] = status_codes([(429, None), (200, None)])
    transport = httpx_retries.RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.post("https://example.com/fail")
        assert response.status_code == 429

    assert mock_sleep.call_count == 0


def test_retries_reset_for_new_request(mock_transport: tuple[MagicMock, dict]) -> None:
    mock_sleep, status_code_sequences = mock_transport
    status_code_sequences["https://example.com/fail"] = status_codes([(429, None)])
    status_code_sequences["https://example.com/fail2"] = status_codes([(429, None)])
    transport = httpx_retries.RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")
        assert response.status_code == 429

        response = client.get("https://example.com/fail2")
        assert response.status_code == 429

    assert mock_sleep.call_count == 20


def test_retry_respects_retry_after_header(mock_transport: tuple[MagicMock, dict]) -> None:
    mock_sleep, status_code_sequences = mock_transport
    status_code_sequences["https://example.com/fail"] = status_codes([(429, "5")])
    transport = httpx_retries.RetryTransport()

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")
        assert response.status_code == 429

    assert mock_sleep.call_count == 10
    mock_sleep.assert_has_calls([call(5)] * 10)


@pytest.mark.asyncio
async def test_async_successful_request(mock_async_transport: tuple[AsyncMock, dict]) -> None:
    mock_asleep, status_code_sequences = mock_async_transport
    transport = httpx_retries.AsyncRetryTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com")

    assert response.status_code == 200
    assert mock_asleep.call_count == 0


@pytest.mark.asyncio
async def test_async_failed_request(mock_async_transport: tuple[AsyncMock, dict]) -> None:
    mock_asleep, status_code_sequences = mock_async_transport
    status_code_sequences["https://example.com/fail"] = astatus_codes([(429, None)])
    transport = httpx_retries.AsyncRetryTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com/fail")

    assert response.status_code == 429
    assert mock_asleep.call_count == 10


@pytest.mark.asyncio
async def test_async_unretryable_method(mock_async_transport: tuple[AsyncMock, dict]) -> None:
    mock_asleep, status_code_sequences = mock_async_transport
    status_code_sequences["https://example.com/fail"] = astatus_codes([(429, None)])
    transport = httpx_retries.AsyncRetryTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.post("https://example.com/fail")

    assert response.status_code == 429
    assert mock_asleep.call_count == 0


@pytest.mark.asyncio
async def test_retries_reset_for_new_request_async(mock_async_transport: tuple[AsyncMock, dict]) -> None:
    mock_asleep, status_code_sequences = mock_async_transport
    status_code_sequences["https://example.com/fail"] = astatus_codes([(429, None)])
    status_code_sequences["https://example.com/fail2"] = astatus_codes([(429, None)])
    transport = httpx_retries.AsyncRetryTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com/fail")
        assert response.status_code == 429

        response = await client.get("https://example.com/fail2")
        assert response.status_code == 429

    assert mock_asleep.call_count == 20


@pytest.mark.asyncio
async def test_retry_respects_retry_after_header_async(mock_async_transport: tuple[AsyncMock, dict]) -> None:
    mock_asleep, status_code_sequences = mock_async_transport
    status_code_sequences["https://example.com/fail"] = astatus_codes([(429, "5")])
    transport = httpx_retries.AsyncRetryTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com/fail")
        assert response.status_code == 429

    assert mock_asleep.call_count == 10
    mock_asleep.assert_has_calls([call(5)] * 10)
