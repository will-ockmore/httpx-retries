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
from typing import Final, Optional, Union

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

    For complex use cases, you can override the `backoff_strategy` method.

    ```python
    class CustomRetry(Retry):
        def backoff_strategy(self) -> float:
            # Custom backoff logic here
            if self.attempts_made == 3:
                return 1.0

            return super().backoff_strategy()
    ```

    Args:
        total (int, optional): The maximum number of times to retry a request before giving up. Defaults to 10.
        max_backoff_wait (float, optional): The maximum time to wait between retries in seconds. Defaults to 120.
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

    # Class constants using Final for better type safety
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
    DEFAULT_MAX_BACKOFF_WAIT: Final[float] = 120.0
    DEFAULT_TOTAL_RETRIES: Final[int] = 10
    DEFAULT_BACKOFF_FACTOR: Final[float] = 0.0
    DEFAULT_BACKOFF_JITTER: Final[float] = 1.0

    def __init__(
        self,
        total: int = DEFAULT_TOTAL_RETRIES,
        allowed_methods: Optional[Iterable[Union[HTTPMethod, str]]] = None,
        status_forcelist: Optional[Iterable[Union[HTTPStatus, int]]] = None,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        respect_retry_after_header: bool = True,
        max_backoff_wait: float = DEFAULT_MAX_BACKOFF_WAIT,
        backoff_jitter: float = DEFAULT_BACKOFF_JITTER,
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

        self.max_attempts = total
        self.backoff_factor = backoff_factor
        self.respect_retry_after_header = respect_retry_after_header
        self.max_backoff_wait = max_backoff_wait
        self.backoff_jitter = backoff_jitter
        self.attempts_made = attempts_made

        # Convert methods and status codes to their proper types
        self.retryable_methods = frozenset(
            HTTPMethod(str(method).upper()) for method in (allowed_methods or self.RETRYABLE_METHODS)
        )
        self.retry_status_codes = frozenset(
            HTTPStatus(int(code)) for code in (status_forcelist or self.RETRYABLE_STATUS_CODES)
        )

    def is_retryable_method(self, method: str) -> bool:
        """Check if a method is retryable."""
        return HTTPMethod(method.upper()) in self.retryable_methods

    def is_retryable_status_code(self, status_code: int) -> bool:
        """Check if a status code is retryable."""
        return HTTPStatus(status_code) in self.retry_status_codes

    def is_retry(self, method: str, status_code: int, has_retry_after: bool) -> bool:
        """
        Check if a method and status code are retryable.

        This functions identically to urllib3's `Retry.is_retry` method.
        """
        return (
            self.max_attempts > 0
            and self.is_retryable_method(method)
            and self.is_retryable_status_code(status_code)
            and not has_retry_after
        )

    def is_exhausted(self) -> bool:
        """Check if the retry attempts have been exhausted."""
        return self.attempts_made >= self.max_attempts

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
                    return min(self.parse_retry_after(retry_after), self.max_backoff_wait)
                except ValueError:
                    logger.warning("Retry-After header is not a valid HTTP date: %s", retry_after)

        # Fall back to backoff strategy
        return self.backoff_strategy() if self.attempts_made > 0 else 0.0

    def sleep(self, response: httpx.Response) -> None:
        """Sleep between retry attempts using the calculated duration."""
        time.sleep(self._calculate_sleep(response.headers))

    async def asleep(self, response: httpx.Response) -> None:
        """Sleep between retry attempts asynchronously using the calculated duration."""
        await asyncio.sleep(self._calculate_sleep(response.headers))

    def increment(self) -> "Retry":
        """Return a new Retry instance with the attempt count incremented."""
        return Retry(
            total=self.max_attempts,
            max_backoff_wait=self.max_backoff_wait,
            backoff_factor=self.backoff_factor,
            respect_retry_after_header=self.respect_retry_after_header,
            allowed_methods=self.retryable_methods,
            status_forcelist=self.retry_status_codes,
            backoff_jitter=self.backoff_jitter,
            attempts_made=self.attempts_made + 1,
        )
