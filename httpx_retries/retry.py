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
from typing import Final, Optional, Tuple, Type, Union

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
        PATCH = "PATCH"
        CONNECT = "CONNECT"


class Retry:
    """
    A class to encapsulate retry logic and configuration.

    Each retry attempt will create a new [Retry][httpx_retries.Retry] object with updated values,
    so they can safely be reused.

    If `backoff_factor` is set, it will use an exponential backoff with configurable jitter.

    For complex use cases, you can override the `backoff_strategy` method.

    Args:
        total (int, optional): The maximum number of times to retry a request before giving up.
        max_backoff_wait (float, optional): The maximum time in seconds to wait between retries.
        backoff_factor (float, optional): The factor by which the wait time increases with each retry attempt.
        respect_retry_after_header (bool, optional): Whether to respect the Retry-After header in HTTP responses
            when deciding how long to wait before retrying.
        allowed_methods (Iterable[http.HTTPMethod, str], optional): The HTTP methods that can be retried. Defaults to
            ["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE"].
        status_forcelist (Iterable[http.HTTPStatus, int], optional): The HTTP status codes that can be retried.
            Defaults to [429, 502, 503, 504].
        retry_on_exceptions (Iterable[Type[httpx.HTTPError]], optional): The HTTP exceptions that can be retried.
            Defaults to [httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError].
        backoff_jitter (float, optional): The amount of jitter to add to the backoff time, between 0 and 1.
            Defaults to 1 (full jitter).
        attempts_made (int, optional): The number of retry attempts already made.
    """

    RETRYABLE_METHODS: Final[frozenset[HTTPMethod]] = frozenset(
        [HTTPMethod.HEAD, HTTPMethod.GET, HTTPMethod.PUT, HTTPMethod.DELETE, HTTPMethod.OPTIONS, HTTPMethod.TRACE]
    )
    RETRYABLE_STATUS_CODES: Final[frozenset[HTTPStatus]] = frozenset(
        [
            HTTPStatus.TOO_MANY_REQUESTS,
            HTTPStatus.BAD_GATEWAY,
            HTTPStatus.SERVICE_UNAVAILABLE,
            HTTPStatus.GATEWAY_TIMEOUT,
        ]
    )
    RETRYABLE_EXCEPTIONS: Final[Tuple[Type[httpx.HTTPError], ...]] = (
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.RemoteProtocolError,
    )

    def __init__(
        self,
        total: int = 10,
        allowed_methods: Optional[Iterable[Union[HTTPMethod, str]]] = None,
        status_forcelist: Optional[Iterable[Union[HTTPStatus, int]]] = None,
        retry_on_exceptions: Optional[Iterable[Type[httpx.HTTPError]]] = None,
        backoff_factor: float = 0.0,
        respect_retry_after_header: bool = True,
        max_backoff_wait: float = 120.0,
        backoff_jitter: float = 1.0,
        attempts_made: int = 0,
    ) -> None:
        """Initialize a new Retry instance."""
        if total < 0:
            raise ValueError("total must be non-negative")
        if backoff_factor < 0:
            raise ValueError("backoff_factor must be non-negative")
        if max_backoff_wait <= 0:
            raise ValueError("max_backoff_wait must be positive")
        if not 0 <= backoff_jitter <= 1:
            raise ValueError("backoff_jitter must be between 0 and 1")
        if attempts_made < 0:
            raise ValueError("attempts_made must be non-negative")

        self.total = total
        self.backoff_factor = backoff_factor
        self.respect_retry_after_header = respect_retry_after_header
        self.max_backoff_wait = max_backoff_wait
        self.backoff_jitter = backoff_jitter
        self.attempts_made = attempts_made

        self.allowed_methods = frozenset(
            HTTPMethod(method.upper()) for method in (allowed_methods or self.RETRYABLE_METHODS)
        )
        self.status_forcelist = frozenset(
            HTTPStatus(int(code)) for code in (status_forcelist or self.RETRYABLE_STATUS_CODES)
        )
        self.retryable_exceptions = (
            self.RETRYABLE_EXCEPTIONS if retry_on_exceptions is None else tuple(retry_on_exceptions)
        )

    def is_retryable_method(self, method: str) -> bool:
        """Check if a method is retryable."""
        return HTTPMethod(method.upper()) in self.allowed_methods

    def is_retryable_status_code(self, status_code: int) -> bool:
        """Check if a status code is retryable."""
        return HTTPStatus(status_code) in self.status_forcelist

    def is_retryable_exception(self, exception: httpx.HTTPError) -> bool:
        """Check if an exception is retryable."""
        return isinstance(exception, self.retryable_exceptions)

    def is_retry(self, method: str, status_code: int, has_retry_after: bool) -> bool:
        """
        Check if a method and status code are retryable.

        This functions identically to urllib3's `Retry.is_retry` method.
        """
        return (
            self.total > 0
            and self.is_retryable_method(method)
            and self.is_retryable_status_code(status_code)
            and not has_retry_after
        )

    def is_exhausted(self) -> bool:
        """Check if the retry attempts have been exhausted."""
        return self.attempts_made >= self.total

    def parse_retry_after(self, retry_after: str) -> float:
        """
        Parse the Retry-After header.

        Args:
            retry_after: The Retry-After header value.

        Returns:
            The number of seconds to wait before retrying.

        Raises:
            ValueError: If the Retry-After header is not a valid number or HTTP date.
        """
        retry_after = retry_after.strip()
        if retry_after.isdigit():
            return float(retry_after)

        try:
            parsed_date = parsedate_to_datetime(retry_after)
            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(tzinfo=datetime.timezone.utc)

            diff = (parsed_date - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            return max(0.0, diff)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid Retry-After header: {retry_after}")

    def backoff_strategy(self) -> float:
        """
        Calculate the backoff time based on the number of attempts.

        For complex use cases, you can override this method to implement a custom backoff strategy.

        ```python
        class CustomRetry(Retry):
            def backoff_strategy(self) -> float:
                if self.attempts_made == 3:
                    return 1.0

                return super().backoff_strategy()
        ```

        Returns:
            The calculated backoff time in seconds, capped by max_backoff_wait.
        """
        if self.backoff_factor == 0:
            return 0.0

        # Calculate exponential backoff
        backoff: float = self.backoff_factor * (2**self.attempts_made)

        # Apply jitter if configured
        if self.backoff_jitter > 0:
            backoff *= random.uniform(1 - self.backoff_jitter, 1)

        return min(backoff, self.max_backoff_wait)

    def _calculate_sleep(self, headers: Union[httpx.Headers, Mapping[str, str]]) -> float:
        """Calculate the sleep duration based on headers and backoff strategy."""
        # Check Retry-After header first if enabled
        if self.respect_retry_after_header:
            retry_after = headers.get("Retry-After", "").strip()
            if retry_after:
                try:
                    retry_after_sleep = min(self.parse_retry_after(retry_after), self.max_backoff_wait)
                    if retry_after_sleep > 0:
                        return retry_after_sleep
                except ValueError:
                    logger.warning("Retry-After header is not a valid HTTP date: %s", retry_after)

        # Fall back to backoff strategy
        return self.backoff_strategy() if self.attempts_made > 0 else 0.0

    def sleep(self, response: Union[httpx.Response, httpx.HTTPError]) -> None:
        """
        Sleep between retry attempts using the calculated duration.

        This method will respect a server’s `Retry-After` response header and sleep the duration
        of the time requested. If that is not present, it will use an exponential backoff. By default,
        the backoff factor is 0 and this method will return immediately.
        """
        time_to_sleep = self._calculate_sleep(response.headers if isinstance(response, httpx.Response) else {})
        logger.debug("sleep seconds=%s", time_to_sleep)
        time.sleep(time_to_sleep)

    async def asleep(self, response: Union[httpx.Response, httpx.HTTPError]) -> None:
        """
        Sleep between retry attempts asynchronously using the calculated duration.

        This method will respect a server’s `Retry-After` response header and sleep the duration
        of the time requested. If that is not present, it will use an exponential backoff. By default,
        the backoff factor is 0 and this method will return immediately.
        """
        time_to_sleep = self._calculate_sleep(response.headers if isinstance(response, httpx.Response) else {})
        logger.debug("asleep seconds=%s", time_to_sleep)
        await asyncio.sleep(self._calculate_sleep(response.headers if isinstance(response, httpx.Response) else {}))

    def increment(self) -> "Retry":
        """Return a new Retry instance with the attempt count incremented."""
        logger.debug("increment retry=%s new_attempts_made=%s", self, self.attempts_made + 1)
        return Retry(
            total=self.total,
            max_backoff_wait=self.max_backoff_wait,
            backoff_factor=self.backoff_factor,
            respect_retry_after_header=self.respect_retry_after_header,
            allowed_methods=self.allowed_methods,
            status_forcelist=self.status_forcelist,
            retry_on_exceptions=self.retryable_exceptions,
            backoff_jitter=self.backoff_jitter,
            attempts_made=self.attempts_made + 1,
        )

    def __repr__(self) -> str:
        return f"<Retry(total={self.total}, attempts_made={self.attempts_made})>"
