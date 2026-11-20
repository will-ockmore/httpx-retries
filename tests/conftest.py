from collections.abc import Awaitable, Callable, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

ResponseValidator = Callable[[httpx.Response], Awaitable[None]]


@pytest.fixture(params=["callable", "wrapper", "awaitable"])
def wrap_async_validator(request: pytest.FixtureRequest) -> Callable[[ResponseValidator], ResponseValidator]:
    def wrap(validate: ResponseValidator) -> ResponseValidator:
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

        validators: dict[str, ResponseValidator] = {
            "callable": AsyncValidator(),
            "wrapper": wrapper,
            "awaitable": ValidationAwaitable,
        }
        return validators[request.param]

    return wrap


@pytest.fixture
def mock_sleep(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_sleep = MagicMock()
    monkeypatch.setattr("time.sleep", mock_sleep)
    return mock_sleep


@pytest.fixture
def mock_asleep(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_asleep = AsyncMock()
    monkeypatch.setattr("anyio.sleep", mock_asleep)
    return mock_asleep
