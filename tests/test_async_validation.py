import asyncio
from collections.abc import Awaitable, Callable, Generator
from typing import Any

import httpx
import pytest

from httpx_retries import Retry, RetryTransport, aretry_request


@pytest.mark.asyncio
@pytest.mark.parametrize("use_helper", [False, True], ids=["transport", "helper"])
@pytest.mark.parametrize("validator_kind", ["callable", "wrapper", "awaitable"])
@pytest.mark.parametrize("retryable", [False, True], ids=["terminal-error", "retry"])
async def test_async_validation_awaits_callback_result(use_helper: bool, validator_kind: str, retryable: bool) -> None:
    requests = 0
    validated: list[str] = []
    error = httpx.ReadTimeout("result not ready") if retryable else ValueError("invalid result")

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, headers={"X-Result": "pending" if requests == 1 else "ready"})

    async def validate(response: httpx.Response) -> None:
        await asyncio.sleep(0)
        assert response.request.url == "https://example.com/result"
        validated.append(response.headers["X-Result"])
        if response.headers["X-Result"] == "pending":
            raise error

    class AsyncValidator:
        async def __call__(self, response: httpx.Response) -> None:
            await validate(response)

    class ValidationAwaitable:
        def __init__(self, response: httpx.Response) -> None:
            self.response = response

        def __await__(self) -> Generator[Any, None, None]:
            return validate(self.response).__await__()

    def wrapper(response: httpx.Response) -> Awaitable[None]:
        return validate(response)

    validators: dict[str, Callable[[httpx.Response], Awaitable[None]]] = {
        "callable": AsyncValidator(),
        "wrapper": wrapper,
        "awaitable": ValidationAwaitable,
    }
    retry = Retry(total=2, validate_response=validators[validator_kind])
    inner = httpx.MockTransport(handle)
    transport = inner if use_helper else RetryTransport(transport=inner, retry=retry)
    async with httpx.AsyncClient(transport=transport) as client:
        if retryable:
            response = (
                await aretry_request(client, "GET", "https://example.com/result", retry=retry)
                if use_helper
                else await client.get("https://example.com/result")
            )
            assert response.headers["X-Result"] == "ready"
        else:
            with pytest.raises(ValueError, match="invalid result") as exc_info:
                if use_helper:
                    await aretry_request(client, "GET", "https://example.com/result", retry=retry)
                else:
                    await client.get("https://example.com/result")
            assert exc_info.value is error

    assert requests == (2 if retryable else 1)
    assert validated == (["pending", "ready"] if retryable else ["pending"])
