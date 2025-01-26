import logging
from collections.abc import Callable, Coroutine
from functools import partial
from typing import Any, Optional

import httpx

from .retry import Retry as Retry

logger = logging.getLogger(__name__)


class RetryTransport(httpx.HTTPTransport):
    """
    A custom HTTP transport that automatically retries requests using the given retry configuration.

    Retry configuration is defined as a [Retry][httpx_retries.Retry] object.

    ```python
    retry = Retry(total=5, backoff_factor=0.5, respect_retry_after_header=False)
    transport = RetryTransport(retry=retry)

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com")
    ```

    Args:
        retry (Retry, optional): The retry configuration.
        **kwargs: Additional arguments passed to httpx.HTTPTransport.

    Attributes:
        retry (Retry): The retry configuration.
    """

    def __init__(
        self,
        retry: Optional[Retry] = None,
        **kwargs: Any,  # HTTPTransport doesn't expose its kwargs type
    ) -> None:
        """
        Initializes a [RetryTransport][httpx_retries.RetryTransport] instance.

        If no retry configuration is provided, a default one will be used; this will retry up to 10 times,
        with no backoff.

        Args:
            retry (Retry, optional):
                The retry configuration.
            **kwargs: Additional arguments passed to httpx.HTTPTransport.
        """
        super().__init__(**kwargs)
        self.retry = retry or Retry()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """
        Sends an HTTP request, possibly with retries.

        Args:
            request (httpx.Request): The request to send.

        Returns:
            httpx.Response: The response received.
        """
        if self.retry.is_retryable_method(request.method):
            send_method = partial(super().handle_request)
            response = self._retry_operation(request, send_method)
        else:
            response = super().handle_request(request)
        return response

    def _retry_operation(
        self,
        request: httpx.Request,
        send_method: Callable[..., httpx.Response],
    ) -> httpx.Response:
        retry = self.retry
        response = None

        while True:
            if response is not None:
                retry.sleep(response)
                retry = retry.increment()

            response = send_method(request)
            if retry.is_exhausted() or not retry.is_retryable_status_code(response.status_code):
                return response


class AsyncRetryTransport(httpx.AsyncHTTPTransport):
    """
    An async HTTP transport that automatically retries requests using the given retry configuration.

    Retry configuration is defined as a [Retry][httpx_retries.Retry] object.

    ```python
    retry = Retry(total=5, backoff_factor=0.5, respect_retry_after_header=False)
    transport = AsyncRetryTransport(retry=retry)

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com")
    ```

    Args:
        retry (Retry, optional): The retry configuration.
        **kwargs: Additional arguments passed to httpx.AsyncHTTPTransport.

    Attributes:
        retry (Retry): The retry configuration.
    """

    def __init__(
        self,
        retry: Optional[Retry] = None,
        **kwargs: Any,  # AsyncHTTPTransport doesn't expose its kwargs type
    ) -> None:
        """
        Initializes an [AsyncRetryTransport][httpx_retries.AsyncRetryTransport] instance.

        If no retry configuration is provided, a default one will be used; this will retry up to 10 times,
        with no backoff.

        Args:
            retry (Retry, optional):
                The retry configuration.
            **kwargs: Additional arguments passed to httpx.AsyncHTTPTransport.
        """
        super().__init__(**kwargs)
        self.retry = retry or Retry()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Sends an HTTP request, possibly with retries.

        Args:
            request: The request to perform.

        Returns:
            The response.
        """
        if self.retry.is_retryable_method(request.method):
            send_method = partial(super().handle_async_request)
            response = await self._retry_operation_async(request, send_method)
        else:
            response = await super().handle_async_request(request)
        return response

    async def _retry_operation_async(
        self,
        request: httpx.Request,
        send_method: Callable[..., Coroutine[Any, Any, httpx.Response]],
    ) -> httpx.Response:
        retry = self.retry
        response = None

        while True:
            if response is not None:
                await retry.asleep(response)
                retry = retry.increment()

            response = await send_method(request)
            if retry.is_exhausted() or not retry.is_retryable_status_code(response.status_code):
                return response
