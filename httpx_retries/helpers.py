import inspect
from typing import Any

import httpx

from .retry import Retry
from .transport import RetryTransport, _retry_operation, _retry_operation_async

# Arguments accepted by `Client.send` rather than `Client.build_request`; forwarded to send if provided.
_SEND_KWARGS = ("auth", "follow_redirects")


def _client_retries(client: httpx.Client | httpx.AsyncClient) -> bool:
    """Return True if the client already retries via a [RetryTransport][httpx_retries.RetryTransport].

    The helpers run the retry loop themselves, so combining them with a retrying transport would retry every
    request twice. Detection reaches into httpx's private attributes and degrades to ``False`` if they are absent.
    """
    mounts = getattr(client, "_mounts", {})
    transports = [getattr(client, "_transport", None), *mounts.values()]
    return any(isinstance(transport, RetryTransport) for transport in transports)


def retry_request(
    client: httpx.Client,
    method: str,
    url: httpx.URL | str,
    *,
    retry: Retry | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """
    Send a request with retries, including errors raised while reading the response body.

    Unlike [RetryTransport][httpx_retries.RetryTransport], which can only observe what flows through its
    `handle_request` method (the response *headers*), this helper drives the retry loop at the client level.
    Because `httpx.Client.send` reads the body before returning, body-phase errors such as `httpx.ReadTimeout`
    and `httpx.RemoteProtocolError("peer closed connection...")` are caught here and retried.

    ```python
    import httpx
    from httpx_retries import retry_request

    with httpx.Client() as client:
        response = retry_request(client, "GET", "https://example.com")
    ```

    The retry configuration can be customised, just like [RetryTransport][httpx_retries.RetryTransport]:

    ```python
    response = retry_request(client, "GET", "https://example.com", retry=Retry(total=5, backoff_factor=0.5))
    ```

    This helper buffers the full response body, so it is not suitable for streaming. Errors raised while
    iterating a streaming response (`client.stream(...)`) cannot be retried.

    Body-phase errors are a niche case; see
    [Why wasn't my `ReadTimeout` retried?](faq.md#why-wasnt-my-readtimeout-retried) for when these helpers are
    worth using and when to prefer [RetryTransport][httpx_retries.RetryTransport] instead.

    Args:
        client: The client used to build and send the request.
        method: The HTTP method.
        url: The URL to request.
        retry: The retry configuration. A per-request `request.extensions["retry"]` takes precedence.
        **kwargs: Additional arguments. `auth` and `follow_redirects` are forwarded to `client.send`; all others
            (for example `params`, `headers`, `json`, `content`) are passed to `client.build_request`.

    Returns:
        The final response.
    """
    if _client_retries(client):
        raise ValueError(
            "retry_request runs the retry loop itself and must be used with a client that does not also retry. "
            "The given client uses RetryTransport, which would retry every request twice. Use a plain "
            "httpx.Client instead; retry_request already retries header-phase errors and retryable status codes."
        )

    send_kwargs = {key: kwargs.pop(key) for key in _SEND_KWARGS if key in kwargs}
    request = client.build_request(method, url, **kwargs)
    retry = request.extensions.setdefault("retry", retry or Retry())

    def send(request: httpx.Request) -> httpx.Response:
        return client.send(request, **send_kwargs)

    if not retry.is_retryable_method(request.method):
        return send(request)

    if retry.validate_response is not None and inspect.iscoroutinefunction(retry.validate_response):
        raise TypeError("validate_response must be a sync function when using a sync client")

    return _retry_operation(request, send, retry)


async def aretry_request(
    client: httpx.AsyncClient,
    method: str,
    url: httpx.URL | str,
    *,
    retry: Retry | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """
    Send a request asynchronously with retries, including errors raised while reading the response body.

    This is the async counterpart to [retry_request][httpx_retries.retry_request]. Body-phase errors are a niche
    case; see [Why wasn't my `ReadTimeout` retried?](faq.md#why-wasnt-my-readtimeout-retried) for when these
    helpers are worth using and when to prefer [RetryTransport][httpx_retries.RetryTransport] instead.

    ```python
    import httpx
    from httpx_retries import aretry_request

    async with httpx.AsyncClient() as client:
        response = await aretry_request(client, "GET", "https://example.com")
    ```

    Args:
        client: The client used to build and send the request.
        method: The HTTP method.
        url: The URL to request.
        retry: The retry configuration. A per-request `request.extensions["retry"]` takes precedence.
        **kwargs: Additional arguments. `auth` and `follow_redirects` are forwarded to `client.send`; all others
            (for example `params`, `headers`, `json`, `content`) are passed to `client.build_request`.

    Returns:
        The final response.
    """
    if _client_retries(client):
        raise ValueError(
            "aretry_request runs the retry loop itself and must be used with a client that does not also retry. "
            "The given client uses RetryTransport, which would retry every request twice. Use a plain "
            "httpx.AsyncClient instead; aretry_request already retries header-phase errors and retryable status "
            "codes."
        )

    send_kwargs = {key: kwargs.pop(key) for key in _SEND_KWARGS if key in kwargs}
    request = client.build_request(method, url, **kwargs)
    retry = request.extensions.setdefault("retry", retry or Retry())

    async def send(request: httpx.Request) -> httpx.Response:
        return await client.send(request, **send_kwargs)

    if not retry.is_retryable_method(request.method):
        return await send(request)

    return await _retry_operation_async(request, send, retry)
