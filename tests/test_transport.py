from collections.abc import AsyncGenerator, Callable, Generator
from typing import Optional, Union
from unittest.mock import AsyncMock, MagicMock, call

import httpx
import pytest
from httpx import Request, Response
from httpx._types import URLTypes

import httpx_retries


class MockTransport(httpx.BaseTransport):
    def __init__(
        self,
        status_code_map: Optional[dict[URLTypes, Optional[Generator[tuple[int, Union[str, None]], None, None]]]] = None,
    ) -> None:
        self.status_code_map = status_code_map or {}

    def handle_request(self, request: Request) -> Response:
        # Simulate failure based on the URL
        status_code_generator = self.status_code_map.get(request.url)

        if status_code_generator is not None:
            status_code, retry_after_header = next(status_code_generator)
        else:
            status_code = 200
            retry_after_header = None
        return Response(
            status_code=status_code,
            request=request,
            headers={"Retry-After": retry_after_header} if retry_after_header else {},
        )


class MockAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        status_code_map: Optional[dict[URLTypes, Optional[AsyncGenerator[tuple[int, Union[str, None]], None]]]] = None,
    ) -> None:
        self.status_code_map = status_code_map or {}

    async def handle_async_request(self, request: Request) -> Response:
        # Get the generator for the URL, if it exists
        status_code_generator = self.status_code_map.get(request.url)

        if status_code_generator is not None:
            # Get the next status code from the generator
            status_code, retry_after_header = await status_code_generator.__anext__()
        else:
            # If the URL is not in the map, return 200
            status_code = 200
            retry_after_header = None

        return Response(
            status_code=status_code,
            request=request,
            headers={"Retry-After": retry_after_header} if retry_after_header else {},
        )


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


MockTransportFixtureFunction = Generator[tuple[Callable[..., MockTransport], MagicMock], None, None]
MockAsyncTransportFixtureFunction = Generator[tuple[Callable[..., MockAsyncTransport], MagicMock], None, None]
MockTransportFixture = tuple[Callable[..., MockTransport], MagicMock]
MockAsyncTransportFixture = tuple[Callable[..., MockAsyncTransport], MagicMock]


@pytest.fixture
def mock_transport(mock_sleep: MagicMock) -> MockTransportFixtureFunction:
    def _mock_transport(
        status_code_map: Optional[dict[URLTypes, Optional[Generator[tuple[int, Union[str, None]], None, None]]]] = None,
    ) -> MockTransport:
        return MockTransport(status_code_map=status_code_map)

    yield _mock_transport, mock_sleep


@pytest.fixture
def mock_async_transport(mock_asleep: MagicMock) -> MockAsyncTransportFixtureFunction:
    def _mock_async_transport(
        status_code_map: Optional[dict[URLTypes, Optional[AsyncGenerator[tuple[int, Union[str, None]], None]]]] = None,
    ) -> MockAsyncTransport:
        return MockAsyncTransport(status_code_map=status_code_map)

    yield _mock_async_transport, mock_asleep


def test_successful_request(mock_transport: MockTransportFixture) -> None:
    get_transport, sleep_mock = mock_transport
    status_code_map = {
        "https://example.com": status_codes([(200, None)]),
    }
    transport = httpx_retries.RetryTransport(wrapped_transport=get_transport(status_code_map=status_code_map))
    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com")

    assert response.status_code == 200
    assert sleep_mock.call_count == 0


def test_failed_request(mock_transport: MockTransportFixture) -> None:
    get_transport, sleep_mock = mock_transport
    transport = httpx_retries.RetryTransport(
        wrapped_transport=get_transport(status_code_map={"https://example.com/fail": status_codes([(429, None)])})
    )

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")

    assert response.status_code == 429
    assert sleep_mock.call_count == 10


def test_unretryable_status_code(mock_transport: MockTransportFixture) -> None:
    status_code_map = {
        "https://example.com/fail": status_codes([(403, None), (200, None)]),
    }
    get_transport, sleep_mock = mock_transport
    transport = httpx_retries.RetryTransport(wrapped_transport=get_transport(status_code_map=status_code_map))
    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")
        assert response.status_code == 403

    assert sleep_mock.call_count == 0


def test_unretryable_method(mock_transport: MockTransportFixture) -> None:
    status_code_map = {
        "https://example.com/fail": status_codes([(429, None), (200, None)]),
    }
    get_transport, sleep_mock = mock_transport
    transport = httpx_retries.RetryTransport(wrapped_transport=get_transport(status_code_map=status_code_map))
    with httpx.Client(transport=transport) as client:
        response = client.post("https://example.com/fail")
        assert response.status_code == 429

    assert sleep_mock.call_count == 0


def test_retries_reset_for_new_request(mock_transport: MockTransportFixture) -> None:
    status_code_map = {
        "https://example.com/fail": status_codes([(429, None)]),
        "https://example.com/fail2": status_codes([(429, None)]),
    }
    get_transport, sleep_mock = mock_transport
    transport = httpx_retries.RetryTransport(wrapped_transport=get_transport(status_code_map=status_code_map))
    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")
        assert response.status_code == 429

        response = client.get("https://example.com/fail2")
        assert response.status_code == 429

    assert sleep_mock.call_count == 20


def test_retry_respects_retry_after_header(mock_transport: MockTransportFixture) -> None:
    get_transport, sleep_mock = mock_transport
    status_code_map = {
        "https://example.com/fail": status_codes([(429, "5")]),
    }
    transport = httpx_retries.RetryTransport(wrapped_transport=get_transport(status_code_map=status_code_map))
    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com/fail")
        assert response.status_code == 429

    assert sleep_mock.call_count == 10
    sleep_mock.assert_has_calls(
        [
            call(5),
            call(5),
            call(5),
            call(5),
            call(5),
            call(5),
            call(5),
            call(5),
            call(5),
        ]
    )


@pytest.mark.asyncio
async def test_async_successful_request(mock_async_transport: MockAsyncTransportFixture) -> None:
    get_transport, sleep_mock = mock_async_transport
    transport = httpx_retries.RetryTransport(wrapped_transport=get_transport())

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com")

    assert response.status_code == 200
    assert sleep_mock.call_count == 0


@pytest.mark.asyncio
async def test_async_failed_request(mock_async_transport: MockAsyncTransportFixture) -> None:
    get_transport, sleep_mock = mock_async_transport
    transport = httpx_retries.RetryTransport(
        wrapped_transport=get_transport(status_code_map={"https://example.com/fail": astatus_codes([(429, None)])})
    )

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com/fail")

    assert response.status_code == 429
    assert sleep_mock.call_count == 10


@pytest.mark.asyncio
async def test_async_unretryable_method(mock_async_transport: MockAsyncTransportFixture) -> None:
    get_transport, sleep_mock = mock_async_transport
    transport = httpx_retries.RetryTransport(
        wrapped_transport=get_transport(status_code_map={"https://example.com/fail": astatus_codes([(429, None)])}),
    )

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.post("https://example.com/fail")

    assert response.status_code == 429
    assert sleep_mock.call_count == 0


@pytest.mark.asyncio
async def test_retries_reset_for_new_request_async(mock_async_transport: MockAsyncTransportFixture) -> None:
    get_transport, sleep_mock = mock_async_transport
    transport = httpx_retries.RetryTransport(
        wrapped_transport=get_transport(
            status_code_map={
                "https://example.com/fail": astatus_codes([(429, None)]),
                "https://example.com/fail2": astatus_codes([(429, None)]),
            }
        ),
    )

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com/fail")
        assert response.status_code == 429

        response = await client.get("https://example.com/fail2")
        assert response.status_code == 429

    assert sleep_mock.call_count == 20


@pytest.mark.asyncio
async def test_retry_respects_retry_after_header_async(mock_async_transport: MockAsyncTransportFixture) -> None:
    get_transport, sleep_mock = mock_async_transport
    transport = httpx_retries.RetryTransport(
        wrapped_transport=get_transport(status_code_map={"https://example.com/fail": astatus_codes([(429, "5")])}),
    )

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com/fail")
        assert response.status_code == 429

    assert sleep_mock.call_count == 10
    sleep_mock.assert_has_calls(
        [call(5), call(5), call(5), call(5), call(5), call(5), call(5), call(5), call(5), call(5)]
    )
