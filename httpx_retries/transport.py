import logging
from collections.abc import Callable, Coroutine
from functools import partial
from typing import Any, Optional, Union

import httpx

from .retry import Retry as Retry

logger = logging.getLogger(__name__)


class RetryTransport(httpx.BaseTransport, httpx.AsyncBaseTransport):
    """
    A transport wrapper that automatically retries requests using the given retry configuration.

    Retry configuration is defined as a [Retry][httpx_retries.Retry] object.

    ```python
    retry = Retry(total=5, backoff_factor=0.5, respect_retry_after_header=False)
    transport = RetryTransport(
        transport=httpx.HTTPTransport(),
        retry=retry
    )

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com")
    ```

    For async usage:
    ```python
    transport = RetryTransport(
        transport=httpx.AsyncHTTPTransport(),
        retry=retry
    )

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://example.com")
    ```

    Args:
        transport: The underlying transport to wrap.
        retry: The retry configuration.

    Attributes:
        retry (Retry): The retry configuration.
        transport: The wrapped transport instance.
    """

    def __init__(
        self,
        transport: Union[httpx.HTTPTransport, httpx.AsyncHTTPTransport],
        retry: Optional[Retry] = None,
    ) -> None:
        self.transport = transport
        self.retry = retry or Retry()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """
        Sends an HTTP request, possibly with retries.

        Args:
            request (httpx.Request): The request to send.

        Returns:
            httpx.Response: The response received.
        """
        if not isinstance(self.transport, httpx.HTTPTransport):
            raise RuntimeError("Synchronous request received but transport is not an instance of httpx.HTTPTransport")

        if self.retry.is_retryable_method(request.method):
            send_method = partial(self.transport.handle_request)
            response = self._retry_operation(request, send_method)
        else:
            response = self.transport.handle_request(request)
        return response

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Sends an HTTP request, possibly with retries.

        Args:
            request: The request to perform.

        Returns:
            The response.
        """
        if not isinstance(self.transport, httpx.AsyncHTTPTransport):
            raise RuntimeError("Async request received but transport is not an instance of httpx.AsyncHTTPTransport")

        if self.retry.is_retryable_method(request.method):
            send_method = partial(self.transport.handle_async_request)
            response = await self._retry_operation_async(request, send_method)
        else:
            response = await self.transport.handle_async_request(request)
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
