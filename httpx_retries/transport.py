import logging
from collections.abc import Callable, Coroutine
from functools import partial
from typing import Any, Optional, Union

import httpx

from .retry import Retry as Retry

logger = logging.getLogger(__name__)


class RetryTransport(httpx.AsyncBaseTransport, httpx.BaseTransport):
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
        retry (Retry, optional): The retry configuration. Defaults to Retry().
        wrapped_transport (Union[httpx.BaseTransport, httpx.AsyncBaseTransport], optional):
            The underlying HTTP transport to wrap and use for making requests.

    Attributes:
        retry (Retry): The retry configuration.
        _wrapped_transport (httpx.BaseTransport, optional): The underlying HTTP transport
            being wrapped.
        _async_wrapped_transport (httpx.AsyncBaseTransport, optional): The underlying HTTP transport
            being wrapped for async requests.

    """

    retry: Retry
    _wrapped_transport: httpx.BaseTransport
    _async_wrapped_transport: httpx.AsyncBaseTransport

    def __init__(
        self,
        retry: Retry = Retry(),
        wrapped_transport: Optional[Union[httpx.BaseTransport, httpx.AsyncBaseTransport]] = None,
    ) -> None:
        """
        Initializes the instance of RetryTransport class with the given parameters.

        Args:
            retry (Retry, optional):
                The retry configuration. Defaults to Retry().
            wrapped_transport (httpx.BaseTransport):
                The transport layer that will be wrapped and retried upon failure.
            async_wrapped_transport (httpx.AsyncBaseTransport):
                The transport layer that will be wrapped and retried upon failure.
        """
        if wrapped_transport:
            if isinstance(wrapped_transport, httpx.BaseTransport):
                self._wrapped_transport = wrapped_transport
            elif isinstance(wrapped_transport, httpx.AsyncBaseTransport):
                self._async_wrapped_transport = wrapped_transport
        else:
            self._wrapped_transport = httpx.HTTPTransport()
            self._async_wrapped_transport = httpx.AsyncHTTPTransport()

        self.retry = retry

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """
        Sends an HTTP request, possibly with retries.

        Args:
            request (httpx.Request): The request to send.

        Returns:
            httpx.Response: The response received.

        """

        if self.retry.is_retryable_method(request.method):
            send_method = partial(self._wrapped_transport.handle_request)
            response = self._retry_operation(request, send_method)
        else:
            response = self._wrapped_transport.handle_request(request)
        return response

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Sends an HTTP request, possibly with retries.

        Args:
            request: The request to perform.

        Returns:
            The response.
        """
        if self.retry.is_retryable_method(request.method):
            send_method = partial(self._async_wrapped_transport.handle_async_request)
            response = await self._retry_operation_async(request, send_method)
        else:
            response = await self._async_wrapped_transport.handle_async_request(request)
        return response

    async def aclose(self) -> None:
        """
        Closes the underlying HTTP transport, terminating all outstanding connections and rejecting any further
        requests.

        This should be called before the object is dereferenced, to ensure that connections are properly cleaned up.
        """
        await self._async_wrapped_transport.aclose()

    def close(self) -> None:
        """
        Closes the underlying HTTP transport, terminating all outstanding connections and rejecting any further
        requests.

        This should be called before the object is dereferenced, to ensure that connections are properly cleaned up.
        """
        self._wrapped_transport.close()

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
