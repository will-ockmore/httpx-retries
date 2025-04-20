import datetime
import logging
from http import HTTPStatus
from typing import List
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import Headers, Response

from httpx_retries.retry import HTTPMethod, Retry


def test_retry_initialization() -> None:
    retry = Retry()
    assert retry.total == 10
    assert retry.backoff_factor == 0
    assert retry.respect_retry_after_header is True
    assert retry.max_backoff_wait == 120


def test_retry_custom_initialization() -> None:
    retry = Retry(
        total=5,
        backoff_factor=0.5,
        respect_retry_after_header=False,
        max_backoff_wait=30,
        allowed_methods=["GET", "POST"],
        status_forcelist=[500, 502],
    )
    assert retry.total == 5
    assert retry.backoff_factor == 0.5
    assert retry.respect_retry_after_header is False
    assert retry.max_backoff_wait == 30
    assert HTTPMethod.GET in retry.allowed_methods
    assert HTTPMethod.POST in retry.allowed_methods
    assert HTTPStatus.INTERNAL_SERVER_ERROR in retry.status_forcelist
    assert HTTPStatus.BAD_GATEWAY in retry.status_forcelist


def test_is_retryable_method() -> None:
    retry = Retry()
    assert retry.is_retryable_method("GET") is True
    assert retry.is_retryable_method("POST") is False


def test_is_retryable_status_code() -> None:
    retry = Retry()
    assert retry.is_retryable_status_code(429) is True
    assert retry.is_retryable_status_code(404) is False


def test_is_retryable_exception() -> None:
    retry = Retry()
    assert retry.is_retryable_exception(httpx.NetworkError("")) is True
    assert retry.is_retryable_exception(httpx.LocalProtocolError("")) is False


def test_custom_retryable_methods_str() -> None:
    retry = Retry(allowed_methods=["POST"])
    assert retry.is_retryable_method("POST") is True
    assert retry.is_retryable_method("GET") is False


def test_custom_retryable_methods_enum() -> None:
    retry = Retry(allowed_methods=[HTTPMethod.POST])
    assert retry.is_retryable_method("POST") is True
    assert retry.is_retryable_method("GET") is False


def test_custom_retry_status_codes() -> None:
    retry = Retry(status_forcelist=[500])
    assert retry.is_retryable_status_code(500) is True
    assert retry.is_retryable_status_code(502) is False


def test_custom_retry_status_codes_enum() -> None:
    retry = Retry(status_forcelist=[HTTPStatus.INTERNAL_SERVER_ERROR])
    assert retry.is_retryable_status_code(500) is True
    assert retry.is_retryable_status_code(502) is False


def test_is_exhausted() -> None:
    retry = Retry(total=3)
    assert retry.is_exhausted() is False

    retry = retry.increment().increment().increment()
    assert retry.is_exhausted() is True


def test_parse_retry_after_seconds() -> None:
    retry = Retry()
    assert retry.parse_retry_after("5") == 5.0


def test_parse_retry_after_http_date() -> None:
    retry = Retry()
    future_date = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=5)).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )
    result = retry.parse_retry_after(future_date)
    assert 3 < result < 7  # Allow some flexibility for test execution time


def test_parse_retry_after_http_date_past() -> None:
    retry = Retry()
    past_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=5)).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )
    result = retry.parse_retry_after(past_date)
    assert result == 0


def test_parse_retry_after_http_date_no_tz() -> None:
    retry = Retry()
    future_date = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=5)).strftime(
        "%a, %d %b %Y %H:%M:%S"
    )
    result = retry.parse_retry_after(future_date)
    assert 3 < result < 7


def test_calculate_sleep_with_retry_after_over_max() -> None:
    retry = Retry(max_backoff_wait=5)
    headers = Headers({"Retry-After": "10"})
    assert retry._calculate_sleep(headers) == 5.0


def test_calculate_sleep_respect_retry_after_false() -> None:
    retry = Retry(respect_retry_after_header=False)
    headers = Headers({"Retry-After": "5"})
    sleep_time = retry._calculate_sleep(headers)
    assert sleep_time <= retry.max_backoff_wait


def test_parse_retry_after_invalid() -> None:
    retry = Retry()
    with pytest.raises(ValueError):
        retry.parse_retry_after("invalid")


def test_calculate_sleep_with_retry_after() -> None:
    retry = Retry()
    headers = Headers({"Retry-After": "5"})
    assert retry._calculate_sleep(headers) == 5.0


def test_calculate_sleep_with_invalid_retry_after(caplog: pytest.LogCaptureFixture) -> None:
    retry = Retry()
    headers = Headers({"Retry-After": "invalid"})
    sleep_time = retry._calculate_sleep(headers)

    assert sleep_time <= retry.max_backoff_wait
    assert "Retry-After header is not a valid HTTP date" in caplog.text


def test_calculate_sleep_returns_immediately_on_first_attempt() -> None:
    retry = Retry()
    headers = Headers({})
    assert retry._calculate_sleep(headers) == 0


def test_sleep_respects_retry_after_header(mock_sleep: MagicMock) -> None:
    retry = Retry()
    response = Response(status_code=429, headers={"Retry-After": "5"})
    retry.sleep(response)
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_with(5.0)


def test_sleep_logs_sleep_time(mock_sleep: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    retry = Retry()
    response = Response(status_code=429, headers={"Retry-After": "5"})
    retry.sleep(response)
    assert "sleep seconds=5.0" in caplog.text


@pytest.mark.asyncio
async def test_asleep_respects_retry_after_header(mock_asleep: AsyncMock) -> None:
    retry = Retry()
    response = Response(status_code=429, headers={"Retry-After": "5"})
    await retry.asleep(response)
    assert mock_asleep.call_count == 1
    mock_asleep.assert_called_with(5.0)


@pytest.mark.asyncio
async def test_asleep_logs_sleep_time(mock_asleep: AsyncMock, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    retry = Retry()
    response = Response(status_code=429, headers={"Retry-After": "5"})
    await retry.asleep(response)
    assert "asleep seconds=5.0" in caplog.text


def test_calculate_sleep_returns_immediately_by_default() -> None:
    # If there is no backoff factor or retry after header, the sleep time should be 0
    retry = Retry(attempts_made=1)
    headers = Headers({})
    assert retry._calculate_sleep(headers) == 0


def test_calculate_sleep_with_backoff() -> None:
    retry = Retry(backoff_factor=2)
    headers = Headers({})
    attempts: List[Retry] = [retry]
    for _ in range(3):
        attempts.append(attempts[-1].increment())

    for i, retry_attempt in enumerate(attempts):
        sleep_time = retry_attempt._calculate_sleep(headers)
        # Backoff should be backoff_factor * (2 ** (attempts))
        # With full jitter, the actual sleep time will be between 0 and this value
        max_expected = 2 * (2 ** (i))
        assert sleep_time <= max_expected


def test_calculate_sleep_falls_back_to_backoff_if_retry_after_is_in_the_past() -> None:
    retry = Retry(backoff_factor=2, attempts_made=2)
    headers = Headers({"Retry-After": "0"})
    sleep_time = retry._calculate_sleep(headers)
    assert sleep_time != 0
    assert sleep_time <= 2 * (2 ** (2))


def test_calculate_sleep_max_backoff() -> None:
    retry = Retry(backoff_factor=2, max_backoff_wait=5)
    headers = Headers({})
    # After several attempts, backoff would exceed max_backoff_wait
    retry = retry.increment().increment().increment()
    sleep_time = retry._calculate_sleep(headers)
    assert sleep_time <= 5


def test_calculate_sleep_first_attempt() -> None:
    retry = Retry(backoff_factor=2)
    headers = Headers({})
    sleep_time = retry._calculate_sleep(headers)
    # First attempt should have no backoff
    assert sleep_time <= 2


def test_calculate_sleep_without_retry_after() -> None:
    retry = Retry()
    headers = Headers({})
    sleep_time = retry._calculate_sleep(headers)

    assert sleep_time <= retry.max_backoff_wait


def test_increment() -> None:
    retry = Retry(total=3)
    new_retry = retry.increment()

    assert new_retry != retry

    assert new_retry.attempts_made == retry.attempts_made + 1
    assert new_retry.total == retry.total
    assert new_retry.backoff_factor == retry.backoff_factor
    assert new_retry.respect_retry_after_header == retry.respect_retry_after_header
    assert new_retry.allowed_methods == retry.allowed_methods
    assert new_retry.status_forcelist == retry.status_forcelist


def test_increment_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    retry = Retry(total=3)
    new_retry = retry.increment()
    assert "increment retry=<Retry(total=3, attempts_made=0)> new_attempts_made=1" in caplog.text
    new_retry.increment()
    assert "increment retry=<Retry(total=3, attempts_made=1)> new_attempts_made=2" in caplog.text


def test_retry_validation_negative_total() -> None:
    with pytest.raises(ValueError, match="total must be non-negative"):
        Retry(total=-1)


def test_retry_validation_negative_backoff_factor() -> None:
    with pytest.raises(ValueError, match="backoff_factor must be non-negative"):
        Retry(backoff_factor=-0.5)


def test_retry_validation_zero_max_backoff_wait() -> None:
    with pytest.raises(ValueError, match="max_backoff_wait must be positive"):
        Retry(max_backoff_wait=0)


def test_retry_validation_negative_max_backoff_wait() -> None:
    with pytest.raises(ValueError, match="max_backoff_wait must be positive"):
        Retry(max_backoff_wait=-1)


def test_retry_validation_invalid_jitter() -> None:
    with pytest.raises(ValueError, match="backoff_jitter must be between 0 and 1"):
        Retry(backoff_jitter=1.5)


def test_retry_validation_negative_jitter() -> None:
    with pytest.raises(ValueError, match="backoff_jitter must be between 0 and 1"):
        Retry(backoff_jitter=-0.5)


def test_retry_validation_negative_attempts() -> None:
    with pytest.raises(ValueError, match="attempts_made must be non-negative"):
        Retry(attempts_made=-1)


def test_method_case_insensitive() -> None:
    retry = Retry(allowed_methods=["get", "POST"])
    assert retry.is_retryable_method("GET")
    assert retry.is_retryable_method("get")
    assert retry.is_retryable_method("POST")
    assert retry.is_retryable_method("post")


def test_backoff_with_no_jitter() -> None:
    retry = Retry(backoff_factor=1, backoff_jitter=0)
    retry = retry.increment()  # One attempt made

    # With no jitter, backoff should be exactly backoff_factor * (2 ** attempts_made)
    assert retry.backoff_strategy() == 2.0


def test_backoff_with_partial_jitter() -> None:
    retry = Retry(backoff_factor=1, backoff_jitter=0.5)
    retry = retry.increment()  # One attempt made

    # With 0.5 jitter, backoff should be between 1.0 and 2.0 times backoff_factor * (2 ** attempts_made)
    backoff = retry.backoff_strategy()
    assert 1.0 <= backoff <= 2.0


def test_zero_backoff_factor() -> None:
    retry = Retry(backoff_factor=0)
    retry = retry.increment()

    assert retry.backoff_strategy() == 0.0


def test_increment_preserves_jitter() -> None:
    retry = Retry(backoff_jitter=0.5)
    new_retry = retry.increment()

    assert new_retry.backoff_jitter == retry.backoff_jitter


def test_retry_after_header_invalid_format() -> None:
    retry = Retry()
    with pytest.raises(ValueError, match="Invalid Retry-After header: invalid date"):
        retry.parse_retry_after("invalid date")


def test_retry_after_header_logging(caplog: pytest.LogCaptureFixture) -> None:
    retry = Retry()
    headers = Headers({"Retry-After": "invalid date"})
    retry._calculate_sleep(headers)

    assert "Retry-After header is not a valid HTTP date: invalid date" in caplog.text


def test_retry_after_header_precedence() -> None:
    retry = Retry(backoff_factor=2)
    retry = retry.increment()  # One attempt made

    # Retry-After header should take precedence over backoff strategy
    headers = Headers({"Retry-After": "1"})
    sleep_time = retry._calculate_sleep(headers)

    assert sleep_time == 1.0


def test_retry_after_respects_max_wait() -> None:
    retry = Retry(max_backoff_wait=1)
    headers = Headers({"Retry-After": "10"})
    sleep_time = retry._calculate_sleep(headers)

    assert sleep_time == 1.0


def test_default_values() -> None:
    retry = Retry()
    assert retry.total == 10
    assert retry.backoff_factor == 0.0
    assert retry.max_backoff_wait == 120.0
    assert retry.backoff_jitter == 1.0


def test_is_retry() -> None:
    retry = Retry(total=3)
    assert retry.is_retry("GET", 429, False) is True
    assert retry.is_retry("POST", 429, False) is False
    assert retry.is_retry("GET", 404, False) is False
    assert retry.is_retry("GET", 429, True) is False

    exhausted_retry = Retry(total=0)
    assert exhausted_retry.is_retry("GET", 429, False) is False


def test_is_retry_custom_configuration() -> None:
    retry = Retry(total=3, allowed_methods=["POST"], status_forcelist=[404])
    assert retry.is_retry("POST", 404, False) is True
    assert retry.is_retry("GET", 404, False) is False
    assert retry.is_retry("POST", 429, False) is False
