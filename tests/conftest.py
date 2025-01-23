from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_sleep(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_sleep = MagicMock()
    monkeypatch.setattr("time.sleep", mock_sleep)
    return mock_sleep


@pytest.fixture
def mock_asleep(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_asleep = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", mock_asleep)
    return mock_asleep
