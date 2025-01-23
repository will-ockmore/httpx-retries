import datetime
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import Headers, Response

from httpx_retries.retry import HTTPMethod, Retry


def test_retry_initialization():
    retry = Retry()
    assert retry.max_attempts == 10
    assert retry.backoff_factor == 0
    assert retry.respect_retry_after_header is True
    assert retry.max_backoff_wait == 120


def test_retry_custom_initialization():
    retry = Retry(
        total=5,
        backoff_factor=0.5,
        respect_retry_after_header=False,
        max_backoff_wait=30,
        allowed_methods=["GET", "POST"],
        status_forcelist=[500, 502],
    )
    assert retry.max_attempts == 5
    assert retry.backoff_factor == 0.5
    assert retry.respect_retry_after_header is False
    assert retry.max_backoff_wait == 30
    assert HTTPMethod.GET in retry.retryable_methods
    assert HTTPMethod.POST in retry.retryable_methods
    assert HTTPStatus.INTERNAL_SERVER_ERROR in retry.retry_status_codes
    assert HTTPStatus.BAD_GATEWAY in retry.retry_status_codes


def test_is_retryable_method():
    retry = Retry()
    assert retry.is_retryable_method("GET") is True
    assert retry.is_retryable_method("POST") is False


def test_is_retryable_status_code():
    retry = Retry()
    assert retry.is_retryable_status_code(429) is True
    assert retry.is_retryable_status_code(404) is False


def test_custom_retryable_methods_str():
    retry = Retry(allowed_methods=["POST"])
    assert retry.is_retryable_method("POST") is True
    assert retry.is_retryable_method("GET") is False


def test_custom_retryable_methods_enum():
    retry = Retry(allowed_methods=[HTTPMethod.POST])
    assert retry.is_retryable_method("POST") is True
    assert retry.is_retryable_method("GET") is False


def test_custom_retry_status_codes():
    retry = Retry(status_forcelist=[500])
    assert retry.is_retryable_status_code(500) is True
    assert retry.is_retryable_status_code(502) is False


def test_custom_retry_status_codes_enum():
    retry = Retry(status_forcelist=[HTTPStatus.INTERNAL_SERVER_ERROR])
    assert retry.is_retryable_status_code(500) is True
    assert retry.is_retryable_status_code(502) is False


def test_is_exhausted():
    retry = Retry(total=3)
    assert retry.is_exhausted() is False

    retry = retry.increment().increment().increment()
    assert retry.is_exhausted() is True


def test_parse_retry_after_seconds():
    retry = Retry()
    assert retry.parse_retry_after("5") == 5.0


def test_parse_retry_after_http_date():
    retry = Retry()
    future_date = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=5)).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )
    result = retry.parse_retry_after(future_date)
    assert 3 < result < 7  # Allow some flexibility for test execution time


def test_parse_retry_after_http_date_past():
    retry = Retry()
    past_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=5)).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )
    result = retry.parse_retry_after(past_date)
    assert result == 0


def test_parse_retry_after_http_date_no_tz():
    retry = Retry()
    future_date = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=5)).strftime(
        "%a, %d %b %Y %H:%M:%S"
    )
    result = retry.parse_retry_after(future_date)
    assert 3 < result < 7


def test_calculate_sleep_with_retry_after_over_max():
    retry = Retry(max_backoff_wait=5)
    headers = Headers({"Retry-After": "10"})
    assert retry._calculate_sleep(headers) == 5.0


def test_calculate_sleep_respect_retry_after_false():
    retry = Retry(respect_retry_after_header=False)
    headers = Headers({"Retry-After": "5"})
    sleep_time = retry._calculate_sleep(headers)
    assert sleep_time <= retry.max_backoff_wait


def test_parse_retry_after_invalid():
    retry = Retry()
    with pytest.raises(ValueError):
        retry.parse_retry_after("invalid")


def test_calculate_sleep_with_retry_after():
    retry = Retry()
    headers = Headers({"Retry-After": "5"})
    assert retry._calculate_sleep(headers) == 5.0


def test_calculate_sleep_with_invalid_retry_after(caplog):
    retry = Retry()
    headers = Headers({"Retry-After": "invalid"})
    sleep_time = retry._calculate_sleep(headers)

    assert sleep_time <= retry.max_backoff_wait
    assert "Retry-After header is not a valid HTTP date" in caplog.text


def test_calculate_sleep_returns_immediately_on_first_attempt():
    retry = Retry()
    headers = Headers({})
    assert retry._calculate_sleep(headers) == 0


def test_sleep_respects_retry_after_header(mock_sleep: MagicMock):
    retry = Retry()
    response = Response(status_code=429, headers={"Retry-After": "5"})
    retry.sleep(response)
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_with(5.0)


@pytest.mark.asyncio
async def test_asleep_respects_retry_after_header(mock_asleep: AsyncMock):
    retry = Retry()
    response = Response(status_code=429, headers={"Retry-After": "5"})
    await retry.asleep(response)
    assert mock_asleep.call_count == 1
    mock_asleep.assert_called_with(5.0)


def test_calculate_sleep_returns_immediately_by_default():
    # If there is no backoff factor or retry after header, the sleep time should be 0
    retry = Retry(attempts_made=1)
    headers = Headers({})
    assert retry._calculate_sleep(headers) == 0


def test_calculate_sleep_with_backoff():
    retry = Retry(backoff_factor=2)
    headers = Headers({})
    attempts = [retry]
    for _ in range(3):
        attempts.append(attempts[-1].increment())

    for i, retry_attempt in enumerate(attempts):
        sleep_time = retry_attempt._calculate_sleep(headers)
        # Backoff should be backoff_factor * (2 ** (attempts))
        # With full jitter, the actual sleep time will be between 0 and this value
        max_expected = 2 * (2 ** (i))
        assert sleep_time <= max_expected


def test_calculate_sleep_max_backoff():
    retry = Retry(backoff_factor=2, max_backoff_wait=5)
    headers = Headers({})
    # After several attempts, backoff would exceed max_backoff_wait
    retry = retry.increment().increment().increment()
    sleep_time = retry._calculate_sleep(headers)
    assert sleep_time <= 5


def test_calculate_sleep_first_attempt():
    retry = Retry(backoff_factor=2)
    headers = Headers({})
    sleep_time = retry._calculate_sleep(headers)
    # First attempt should have no backoff
    assert sleep_time <= 2


def test_calculate_sleep_without_retry_after():
    retry = Retry()
    headers = Headers({})
    sleep_time = retry._calculate_sleep(headers)

    assert sleep_time <= retry.max_backoff_wait


def test_increment():
    retry = Retry(total=3)
    new_retry = retry.increment()

    assert new_retry != retry

    assert new_retry.attempts_made == retry.attempts_made + 1
    assert new_retry.max_attempts == retry.max_attempts
    assert new_retry.backoff_factor == retry.backoff_factor
    assert new_retry.respect_retry_after_header == retry.respect_retry_after_header
    assert new_retry.retryable_methods == retry.retryable_methods
    assert new_retry.retry_status_codes == retry.retry_status_codes
