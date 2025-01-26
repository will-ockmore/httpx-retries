import logging
from collections.abc import Callable, Coroutine
from functools import partial
from typing import Any, Optional, Union

import httpx

from .retry import Retry as Retry

logger = logging.getLogger(__name__)


class RetryTransport(httpx.BaseTransport, httpx.AsyncBaseTransport):
    """
    A transport that automatically retries requests using the given retry configuration.

    Retry configuration is defined as a [Retry][httpx_retries.Retry] object.

    ```python
    with httpx.Client(transport=RetryTransport()) as client:
        response = client.get("https://example.com")

    async with httpx.AsyncClient(transport=RetryTransport()) as client:
        response = await client.get("https://example.com")
    ```

    If you want to use a specific retry strategy, provide a [Retry][httpx_retries.Retry] configuration:

    ```python
    retry = Retry(total=5, backoff_factor=0.5)
    transport = RetryTransport(retry=retry)

    with httpx.Client(transport=transport) as client:
        response = client.get("https://example.com")
    ```

    Args:
        transport: Optional transport to wrap. If not provided, async and sync transports are created internally.
        retry: The retry configuration.
    """

    def __init__(
        self,
        transport: Optional[Union[httpx.HTTPTransport, httpx.AsyncHTTPTransport]] = None,
        retry: Optional[Retry] = None,
    ) -> None:
        self.retry = retry or Retry()

        if transport is not None:
            self._sync_transport = transport if isinstance(transport, httpx.HTTPTransport) else None
            self._async_transport = transport if isinstance(transport, httpx.AsyncHTTPTransport) else None
        else:
            self._sync_transport = httpx.HTTPTransport()
            self._async_transport = httpx.AsyncHTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """
        Sends an HTTP request, possibly with retries.

        Args:
            request (httpx.Request): The request to send.

        Returns:
            httpx.Response: The response received.
        """
        if self._sync_transport is None:
            raise RuntimeError("Synchronous request received but no sync transport available")

        if self.retry.is_retryable_method(request.method):
            send_method = partial(self._sync_transport.handle_request)
            response = self._retry_operation(request, send_method)
        else:
            response = self._sync_transport.handle_request(request)
        return response

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Sends an HTTP request, possibly with retries.

        Args:
            request: The request to perform.

        Returns:
            The response.
        """
        if self._async_transport is None:
            raise RuntimeError("Async request received but no async transport available")

        if self.retry.is_retryable_method(request.method):
            send_method = partial(self._async_transport.handle_async_request)
            response = await self._retry_operation_async(request, send_method)
        else:
            response = await self._async_transport.handle_async_request(request)
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
