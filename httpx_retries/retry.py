import asyncio
import datetime
import logging
import random
import sys
import time
from collections.abc import Iterable, Mapping
from email.utils import parsedate_to_datetime
from enum import Enum
from http import HTTPStatus
from typing import Optional, Union

import httpx

logger = logging.getLogger(__name__)

if sys.version_info >= (3, 11):
    from http import HTTPMethod as HTTPMethod
else:  # pragma: no cover

    class HTTPMethod(str, Enum):
        HEAD = "HEAD"
        GET = "GET"
        POST = "POST"
        PUT = "PUT"
        DELETE = "DELETE"
        OPTIONS = "OPTIONS"
        TRACE = "TRACE"


class Retry:
    """
    A class to encapsulate retry logic and configuration.

    Each retry attempt will create a new [Retry][httpx_retries.Retry] object with updated values,
    so they can safely be reused.

    If `backoff_factor` is set, it will use an exponential backoff with configurable jitter.

    For complex use cases, you can subclass this class and override the `backoff_strategy` method.

    ```python
    class CustomRetry(Retry):
        def backoff_strategy(self) -> float:
            # Custom backoff logic here
            return 1.0
    ```

    Args:
        total (int, optional): The maximum number of times to retry a request before giving up. Defaults to 10.
        max_backoff_wait (float, optional): The maximum time to wait between retries in seconds. Defaults to 60.
        backoff_factor (float, optional): The factor by which the wait time increases with each retry attempt.
            Defaults to 0.
        respect_retry_after_header (bool, optional): Whether to respect the Retry-After header in HTTP responses
            when deciding how long to wait before retrying. Defaults to True.
        allowed_methods (Iterable[http.HTTPMethod, str], optional): The HTTP methods that can be retried. Defaults to
            ["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE"].
        status_forcelist (Iterable[http.HTTPStatus, int], optional): The HTTP status codes that can be retried.
            Defaults to [429, 502, 503, 504].
        backoff_jitter (float, optional): The amount of jitter to add to the backoff time. Defaults to 1 (full jitter).
        attempts_made (int, optional): The number of attempts already made. Defaults to 0.
    """

    RETRYABLE_METHODS = frozenset(
        [HTTPMethod.HEAD, HTTPMethod.GET, HTTPMethod.PUT, HTTPMethod.DELETE, HTTPMethod.OPTIONS, HTTPMethod.TRACE]
    )
    RETRYABLE_STATUS_CODES = frozenset(
        [
            HTTPStatus.TOO_MANY_REQUESTS,
            HTTPStatus.BAD_GATEWAY,
            HTTPStatus.SERVICE_UNAVAILABLE,
            HTTPStatus.GATEWAY_TIMEOUT,
        ]
    )
    MAX_BACKOFF_WAIT = 120

    def __init__(
        self,
        total: int = 10,
        allowed_methods: Optional[Iterable[Union[HTTPMethod, str]]] = None,
        status_forcelist: Optional[Iterable[Union[HTTPStatus, int]]] = None,
        backoff_factor: float = 0,
        respect_retry_after_header: bool = True,
        max_backoff_wait: float = MAX_BACKOFF_WAIT,
        backoff_jitter: float = 1,
        attempts_made: int = 0,
    ) -> None:
        self.max_attempts = total
        self.backoff_factor = backoff_factor
        self.respect_retry_after_header = respect_retry_after_header
        self.retryable_methods = (
            frozenset(HTTPMethod(method) for method in allowed_methods) if allowed_methods else self.RETRYABLE_METHODS
        )
        self.retry_status_codes = (
            frozenset(HTTPStatus(status_code) for status_code in status_forcelist)
            if status_forcelist
            else self.RETRYABLE_STATUS_CODES
        )
        self.max_backoff_wait = max_backoff_wait
        self.backoff_jitter = backoff_jitter
        self.attempts_made = attempts_made

    def is_retryable_method(self, method: str) -> bool:
        """
        Check if a method is retryable.

        Args:
            method (str): The HTTP method to check.

        Returns:
            bool: True if the method is retryable, False otherwise.
        """
        return method in self.retryable_methods

    def is_retryable_status_code(self, status_code: int) -> bool:
        """
        Check if a status code is retryable.

        Args:
            status_code (int): The HTTP status code to check.

        Returns:
            bool: True if the status code is retryable, False otherwise.
        """
        return status_code in self.retry_status_codes

    def is_exhausted(self) -> bool:
        """
        Check if the retry attempts have been exhausted.

        Returns:
            bool: True if the retry attempts have been exhausted, False otherwise.
        """
        return self.attempts_made >= self.max_attempts

    def parse_retry_after(self, retry_after: str) -> float:
        """
        Parse the Retry-After header.

        Args:
            retry_after (str): The Retry-After header value.

        Returns:
            float: The number of seconds to wait before retrying.
        """
        if retry_after.isdigit():
            return float(retry_after)

        try:
            parsed_date = parsedate_to_datetime(retry_after)
        except TypeError:
            # This is to ensure the behaviour in python 3.9 matches the recent versions.
            # See https://github.com/python/cpython/pull/22090
            # For this reason, the following two lines can't be included in coverage.
            raise ValueError("Retry-After header is not a valid HTTP date")  # pragma: no cover
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=datetime.timezone.utc)  # pragma: no cover
        diff = (parsed_date - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        if diff > 0:
            return diff

        return 0

    def backoff_strategy(self) -> float:
        """
        Return the backoff time based on the number of attempts.

        If `backoff_factor` is set, it will use an exponential backoff with configurable jitter;
        otherwise, it will return 0 (no backoff).
        """
        backoff: float = self.backoff_factor * (2 ** (self.attempts_made))
        if self.backoff_jitter:
            backoff = backoff * random.uniform(0, self.backoff_jitter)
        return min(backoff, self.max_backoff_wait)

    def _calculate_sleep(self, headers: Union[httpx.Headers, Mapping[str, str]]) -> float:
        retry_after_header = (headers.get("Retry-After") or "").strip()
        if self.respect_retry_after_header and retry_after_header:
            try:
                retry_after = self.parse_retry_after(retry_after_header)
                return min(retry_after, self.max_backoff_wait)
            except ValueError:
                # The behaviour for an invalid Retry-After header is the same as if no Retry-After header was present.
                # A warning is logged to indicate the issue.
                logger.warning("Retry-After header is not a valid HTTP date: %s", retry_after_header)

        if self.attempts_made == 0:
            return 0

        return self.backoff_strategy()

    def sleep(self, response: httpx.Response) -> None:
        """
        Sleep between retry attempts.

        This method will respect a server’s Retry-After response header and sleep the duration of the time requested.
        If that is not present, it will use an exponential backoff.
        By default, the backoff factor is 0 and this method will return immediately.
        """
        time.sleep(self._calculate_sleep(response.headers))

    async def asleep(self, response: httpx.Response) -> None:
        """
        Sleep between retry attempts.

        This is the async version of the `sleep` method.

        This method will respect a server’s Retry-After response header and sleep the duration of the time requested.
        If that is not present, it will use an exponential backoff.
        By default, the backoff factor is 0 and this method will return immediately.
        """
        await asyncio.sleep(self._calculate_sleep(response.headers))

    def increment(self) -> "Retry":
        """
        Return a new Retry instance with the attempt count incremented.
        """
        return Retry(
            total=self.max_attempts,
            max_backoff_wait=self.max_backoff_wait,
            backoff_factor=self.backoff_factor,
            respect_retry_after_header=self.respect_retry_after_header,
            allowed_methods=self.retryable_methods,
            status_forcelist=self.retry_status_codes,
            attempts_made=self.attempts_made + 1,
        )
