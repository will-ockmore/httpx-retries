from collections.abc import AsyncIterator, Generator, Iterator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from httpx_retries import Retry, RetryTransport, aretry_request, retry_request


class _FailingByteStream(httpx.SyncByteStream):
    """A response body that raises when read."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __iter__(self) -> Iterator[bytes]:
        raise self._exc
        yield b""  # pragma: no cover

    def close(self) -> None:
        pass


class _FailingAsyncByteStream(httpx.AsyncByteStream):
    """A response body that raises when read."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def __aiter__(self) -> AsyncIterator[bytes]:
        raise self._exc
        yield b""  # pragma: no cover

    async def aclose(self) -> None:
        pass


class BodyFailTransport(httpx.BaseTransport):
    """Returns a response whose body read fails `fail_times` times, then succeeds."""

    def __init__(self, exc: Exception, fail_times: int) -> None:
        self.exc = exc
        self.fail_times = fail_times
        self.attempts = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            return httpx.Response(200, stream=_FailingByteStream(self.exc))
        return httpx.Response(200, content=b"ok")


class AsyncBodyFailTransport(httpx.AsyncBaseTransport):
    """Returns a response whose body read fails `fail_times` times, then succeeds."""

    def __init__(self, exc: Exception, fail_times: int) -> None:
        self.exc = exc
        self.fail_times = fail_times
        self.attempts = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            return httpx.Response(200, stream=_FailingAsyncByteStream(self.exc))
        return httpx.Response(200, content=b"ok")


class _HeaderAuth(httpx.Auth):
    """Auth scheme that stamps a fixed header onto each request."""

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["X-Auth"] = "secret"
        yield request


class RecordingTransport(httpx.BaseTransport):
    """Records the requests it receives and returns 200."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, content=b"ok")


class AsyncRecordingTransport(httpx.AsyncBaseTransport):
    """Records the requests it receives and returns 200."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, content=b"ok")


class RedirectTransport(httpx.BaseTransport):
    """Redirects `/start` to `/final` once, then serves `/final`."""

    def __init__(self) -> None:
        self.paths: list[str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "https://example.com/final"})
        return httpx.Response(200, content=b"final")


class AsyncRedirectTransport(httpx.AsyncBaseTransport):
    """Redirects `/start` to `/final` once, then serves `/final`."""

    def __init__(self) -> None:
        self.paths: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "https://example.com/final"})
        return httpx.Response(200, content=b"final")


def test_retry_request_success(mock_sleep: MagicMock) -> None:
    transport = BodyFailTransport(httpx.ReadTimeout("boom"), fail_times=0)

    with httpx.Client(transport=transport) as client:
        response = retry_request(client, "GET", "https://example.com")

    assert response.status_code == 200
    assert response.text == "ok"
    assert mock_sleep.call_count == 0
    assert response.extensions["retry"].attempts_made == 0


def test_retry_request_retries_body_read_error(mock_sleep: MagicMock) -> None:
    transport = BodyFailTransport(httpx.ReadTimeout("boom"), fail_times=2)

    with httpx.Client(transport=transport) as client:
        response = retry_request(client, "GET", "https://example.com")

    assert response.status_code == 200
    assert response.text == "ok"
    assert transport.attempts == 3
    assert mock_sleep.call_count == 2
    assert response.extensions["retry"].attempts_made == 2


def test_retry_request_raises_when_exhausted(mock_sleep: MagicMock) -> None:
    transport = BodyFailTransport(httpx.ReadTimeout("boom"), fail_times=100)
    retry = Retry(total=3)

    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ReadTimeout, match="boom"):
            retry_request(client, "GET", "https://example.com", retry=retry)

    assert mock_sleep.call_count == 3


def test_retry_request_non_retryable_method(mock_sleep: MagicMock) -> None:
    transport = BodyFailTransport(httpx.ReadTimeout("boom"), fail_times=1)

    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ReadTimeout, match="boom"):
            retry_request(client, "POST", "https://example.com")

    assert transport.attempts == 1
    assert mock_sleep.call_count == 0


def test_retry_request_extension_overrides_retry_argument(mock_sleep: MagicMock) -> None:
    transport = BodyFailTransport(httpx.ReadTimeout("boom"), fail_times=100)

    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ReadTimeout, match="boom"):
            retry_request(
                client,
                "GET",
                "https://example.com",
                retry=Retry(total=10),
                extensions={"retry": Retry(total=2)},
            )

    assert mock_sleep.call_count == 2


def test_retry_request_async_validate_response_raises_for_sync_client() -> None:
    async def validate(response: httpx.Response) -> None:  # pragma: no cover
        pass

    transport = BodyFailTransport(httpx.ReadTimeout("boom"), fail_times=0)
    retry = Retry(validate_response=validate)

    with httpx.Client(transport=transport) as client:
        with pytest.raises(TypeError, match="validate_response must be a sync function"):
            retry_request(client, "GET", "https://example.com", retry=retry)


@pytest.mark.asyncio
async def test_aretry_request_success(mock_asleep: AsyncMock) -> None:
    transport = AsyncBodyFailTransport(httpx.ReadTimeout("boom"), fail_times=0)

    async with httpx.AsyncClient(transport=transport) as client:
        response = await aretry_request(client, "GET", "https://example.com")

    assert response.status_code == 200
    assert response.text == "ok"
    assert mock_asleep.call_count == 0


@pytest.mark.asyncio
async def test_aretry_request_retries_body_read_error(mock_asleep: AsyncMock) -> None:
    transport = AsyncBodyFailTransport(httpx.ReadTimeout("boom"), fail_times=2)

    async with httpx.AsyncClient(transport=transport) as client:
        response = await aretry_request(client, "GET", "https://example.com")

    assert response.status_code == 200
    assert response.text == "ok"
    assert transport.attempts == 3
    assert mock_asleep.call_count == 2
    assert response.extensions["retry"].attempts_made == 2


@pytest.mark.asyncio
async def test_aretry_request_non_retryable_method(mock_asleep: AsyncMock) -> None:
    transport = AsyncBodyFailTransport(httpx.ReadTimeout("boom"), fail_times=1)

    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.ReadTimeout, match="boom"):
            await aretry_request(client, "POST", "https://example.com")

    assert transport.attempts == 1
    assert mock_asleep.call_count == 0


def test_retry_request_forwards_auth(mock_sleep: MagicMock) -> None:
    transport = RecordingTransport()

    with httpx.Client(transport=transport) as client:
        response = retry_request(client, "GET", "https://example.com", auth=_HeaderAuth())

    assert response.status_code == 200
    assert transport.requests[0].headers["X-Auth"] == "secret"


def test_retry_request_forwards_follow_redirects(mock_sleep: MagicMock) -> None:
    transport = RedirectTransport()

    with httpx.Client(transport=transport) as client:
        # Without follow_redirects, the client default (off) leaves the 302 in place.
        response = retry_request(client, "GET", "https://example.com/start")
        assert response.status_code == 302

        response = retry_request(client, "GET", "https://example.com/start", follow_redirects=True)

    assert response.status_code == 200
    assert response.text == "final"
    assert transport.paths == ["/start", "/start", "/final"]


@pytest.mark.asyncio
async def test_aretry_request_forwards_auth(mock_asleep: AsyncMock) -> None:
    transport = AsyncRecordingTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await aretry_request(client, "GET", "https://example.com", auth=_HeaderAuth())

    assert response.status_code == 200
    assert transport.requests[0].headers["X-Auth"] == "secret"


@pytest.mark.asyncio
async def test_aretry_request_forwards_follow_redirects(mock_asleep: AsyncMock) -> None:
    transport = AsyncRedirectTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        response = await aretry_request(client, "GET", "https://example.com/start", follow_redirects=True)

    assert response.status_code == 200
    assert response.text == "final"
    assert transport.paths == ["/start", "/final"]


def test_retry_request_rejects_retrying_client() -> None:
    with httpx.Client(transport=RetryTransport(transport=RecordingTransport())) as client:
        with pytest.raises(ValueError, match="would retry every request twice"):
            retry_request(client, "GET", "https://example.com")


def test_retry_request_rejects_mounted_retrying_transport() -> None:
    mounts = {"https://": RetryTransport(transport=RecordingTransport())}
    with httpx.Client(mounts=mounts, trust_env=False) as client:
        with pytest.raises(ValueError, match="would retry every request twice"):
            retry_request(client, "GET", "https://example.com")


@pytest.mark.asyncio
async def test_aretry_request_rejects_retrying_client() -> None:
    async with httpx.AsyncClient(transport=RetryTransport(transport=AsyncRecordingTransport())) as client:
        with pytest.raises(ValueError, match="would retry every request twice"):
            await aretry_request(client, "GET", "https://example.com")
