import logging
from collections.abc import Callable, Coroutine
from functools import partial
from typing import Any, Optional, Union

import httpx

from .retry import Retry as Retry

logger = logging.getLogger(__name__)


class RetryTransport(httpx.BaseTransport, httpx.AsyncBaseTransport):
    """
    A transport that automatically retries requests.

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

    By default, the implementation will create a sync and async transport internally, and use whichever is appropriate
    for the request. If you want to configure your own transport, provide it to the `transport` argument:

    ```python
    transport = RetryTransport(transport=httpx.HTTPTransport(local_address="0.0.0.0"))
    ```

    Args:
        transport: Optional transport to wrap. If not provided, async and sync transports are created internally.
        retry: The retry configuration.
    """

    def __init__(
        self,
        transport: Optional[Union[httpx.BaseTransport, httpx.AsyncBaseTransport]] = None,
        retry: Optional[Retry] = None,
    ) -> None:
        self.retry = retry or Retry()

        if transport is not None:
            self._sync_transport = transport if isinstance(transport, httpx.BaseTransport) else None
            self._async_transport = transport if isinstance(transport, httpx.AsyncBaseTransport) else None
        else:
            self._sync_transport = httpx.HTTPTransport()
            self._async_transport = httpx.AsyncHTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """
        Sends an HTTP request, possibly with retries.

        Args:
            request (httpx.Request): The request to send.

        Returns:
            The final response.
        """
        if self._sync_transport is None:
            raise RuntimeError("Synchronous request received but no sync transport available")

        logger.debug("handle_request started request=%s", request)

        if self.retry.is_retryable_method(request.method):
            send_method = partial(self._sync_transport.handle_request)
            response = self._retry_operation(request, send_method)
        else:
            response = self._sync_transport.handle_request(request)

        logger.debug("handle_request finished request=%s response=%s", request, response)

        return response

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Sends an HTTP request, possibly with retries.

        Args:
            request: The request to perform.

        Returns:
            The final response.
        """
        if self._async_transport is None:
            raise RuntimeError("Async request received but no async transport available")

        logger.debug("handle_async_request started request=%s", request)

        if self.retry.is_retryable_method(request.method):
            send_method = partial(self._async_transport.handle_async_request)
            response = await self._retry_operation_async(request, send_method)
        else:
            response = await self._async_transport.handle_async_request(request)

        logger.debug("handle_async_request finished request=%s response=%s", request, response)

        return response

    def _retry_operation(
        self,
        request: httpx.Request,
        send_method: Callable[..., httpx.Response],
    ) -> httpx.Response:
        retry = self.retry
        response: Union[httpx.Response, httpx.HTTPError, None] = None

        while True:
            if response is not None:
                logger.debug("_retry_operation retrying request=%s response=%s retry=%s", request, response, retry)
                retry = retry.increment()
                retry.sleep(response)
            try:
                response = send_method(request)
            except httpx.HTTPError as e:
                if retry.is_exhausted() or not retry.is_retryable_exception(e):
                    raise

                response = e
                continue

            if retry.is_exhausted() or not retry.is_retryable_status_code(response.status_code):
                return response

    async def _retry_operation_async(
        self,
        request: httpx.Request,
        send_method: Callable[..., Coroutine[Any, Any, httpx.Response]],
    ) -> httpx.Response:
        retry = self.retry
        response: Union[httpx.Response, httpx.HTTPError, None] = None

        while True:
            if response is not None:
                logger.debug(
                    "_retry_operation_async retrying request=%s response=%s retry=%s", request, response, retry
                )
                retry = retry.increment()
                await retry.asleep(response)
            try:
                response = await send_method(request)
            except httpx.HTTPError as e:
                if retry.is_exhausted() or not retry.is_retryable_exception(e):
                    raise

                response = e
                continue

            if retry.is_exhausted() or not retry.is_retryable_status_code(response.status_code):
                return response
