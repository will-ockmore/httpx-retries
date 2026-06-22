# FAQs

On this page are some examples of usage and commonly asked questions.

## Chaining transports

HTTPX Retries is implemented as a [custom Transport](https://www.python-httpx.org/advanced/transports/#custom-transports).
It's common to want to add additional custom behaviour (eg. rate-limiting, proxies and more), and it's
possible to chain transports to layer in behaviours; the first argument to the [RetryTransport][httpx_retries.RetryTransport]
constructor is a transport to wrap.

``` python
with AsyncClient(
    transport=RetryTransport(
        RateLimitTransport(
            AsyncHTTPTransport(),
            interval=timedelta(seconds=1),
            count=3,
        ),
        retry=Retry(total=5, backoff_factor=0.5),
    ),
    timeout=90.0,
) as client:
    ...
```

## Client timeout or [Retry][httpx_retries.Retry] timeout?

Does the `httpx.Client` timeout apply to each request made in a series of retries, or to the "user request", who wants
the result in the next 10s, regardless of how many times the underlying HTTP client needs to try to get it?

The timeout passed to `httpx.Client` applies to each request in a series of retries. If a `httpx.TimeoutException` is
raised and a retry is applicable, the same request, with the same timeout values, will be retried.

In the case where retries are bounded by individual (client) timeouts, it is always possible to work out the
maximum possible time taken to execute all retries.

So if you wanted to add a lower overall retry value than the number of retries multiplied by the client timeout, you
could tweak the max_backoff_wait and backoff_factor. Eg.

```python
Retry(total=3, max_backoff_wait=5.0, backoff_factor=1, jitter=0)
```

would result in a retry-inclusive timeout of `15s + 3 * (client_timeout)`.

## Why wasn't my `ReadTimeout` retried?

If an error like `httpx.ReadTimeout` or `httpx.RemoteProtocolError("peer closed connection without sending complete message body")` escapes your client with no retry attempts logged, this is expected given HTTPX's transport architecture, not a bug in `RetryTransport`.

HTTPX transports return as soon as response *headers* are received. The response *body* is read lazily inside the client — by `response.read()`, `response.aread()`, or iteration over a streaming response. Errors that occur while reading the body are raised directly to the caller, bypassing the transport. Since [RetryTransport][httpx_retries.RetryTransport] only observes what flows through its `handle_request` / `handle_async_request` methods, it cannot retry these body-phase errors.

Retried by [RetryTransport][httpx_retries.RetryTransport]:

- `httpx.TimeoutException`, `httpx.NetworkError`, and `httpx.RemoteProtocolError` raised **before** response headers arrive (for example, a connect timeout, or a slow server that doesn't send headers in time).
- Responses with a retryable status code (default: `429`, `502`, `503`, `504`).

Not retried by [RetryTransport][httpx_retries.RetryTransport]:

- Any exception raised during `response.read()`, `response.aread()`, or iteration of a streaming response — including `ReadTimeout` mid-body and `RemoteProtocolError("peer closed connection...")`.

To retry body-phase errors, use [retry_request][httpx_retries.retry_request] (or its async counterpart [aretry_request][httpx_retries.aretry_request]). These helpers drive the retry loop at the *client* level, where the body is read, so the same [Retry][httpx_retries.Retry] configuration covers body-phase errors as well as the header-phase errors and retryable status codes that [RetryTransport][httpx_retries.RetryTransport] already handles:

```python
import httpx
from httpx_retries import Retry, retry_request

with httpx.Client() as client:
    response = retry_request(client, "GET", "https://example.com", retry=Retry(total=5, backoff_factor=0.5))
```

```python
import httpx
from httpx_retries import aretry_request

async with httpx.AsyncClient() as client:
    response = await aretry_request(client, "GET", "https://example.com")
```

A plain client is all you need — the helpers run the full retry loop themselves, so there's no need to also install [RetryTransport][httpx_retries.RetryTransport]. Passing a client that uses [RetryTransport][httpx_retries.RetryTransport] raises a `ValueError`, because it would retry every request twice.

!!! warning "These helpers buffer the full response body"
    Because the body is read before the helper returns, `retry_request` and `aretry_request` are not suitable for streaming. An error raised while iterating a streaming response (`client.stream(...)`) happens after the body has started arriving and cannot be retried transparently — bytes already handed to your code can't be recalled. For streaming, catch the error and re-issue the request yourself.

!!! note "Only idempotent methods are retried by default"
    Like [RetryTransport][httpx_retries.RetryTransport], the helpers only retry methods in `Retry.allowed_methods` (by default `HEAD`, `GET`, `PUT`, `DELETE`, `OPTIONS`, `TRACE`); other methods are sent once. You can opt a method in with `Retry(allowed_methods=[...])`, but take care: a body-phase retry re-issues the *entire* request, and because the server has already started responding it has most likely processed the original — so only enable non-idempotent methods such as `POST` when duplicate side effects are acceptable.

## Retrying on response content

Sometimes a server returns a valid response but the body or custom headers signals a failure - for example, a block page, a CAPTCHA redirect, or an authorization wall. This commonly occurs if access may be blocked at the content level rather than the HTTP status level.

Use `validate_response` to inspect the response and raise an exception to trigger a retry:

```python
import httpx
from httpx_retries import Retry, RetryTransport

class ContentBlocked(ValueError):
    pass

def validate_response(response: httpx.Response) -> None:
    # safely inspect status and headers if needed
    response.raise_for_status()

    # NOTE: Do not call `.read()` here with `Client.stream`,
    # it will buffer the entire body, which defeats the purpose of streaming.
    response.read()
    if "content blocked" in response.text:
        raise ContentBlocked(response.text)

retry = Retry(validate_response=validate_response, retry_on_exceptions=[httpx.HTTPStatusError, ContentBlocked])

with httpx.Client(transport=RetryTransport(retry=retry)) as client:
    response = client.get("https://example.com")
```

!!! warning "Do not call `response.read()` inside `validate_response` with `Client.stream`"
    `validate_response` is called before the response is returned to the caller. Calling `response.read()` or `await response.aread()` inside it will buffer the entire body, which defeats the purpose of streaming. If you use streaming, validate only the status code and headers.

## Limits / Cert / SSL / http2 parameters passed to the client are not being applied

This is a limitation of the way transports are applied to clients in HTTPX. If you provide a custom transport, several parameters
that can be passed to `httpx.Client` are ignored. The workaround is to directly provide an instance of
[httpx.HTTPTransport](https://www.python-httpx.org/advanced/transports/#http-transport) (or the async variant) which
will accept these parameters.

```python
with Client(
    transport=RetryTransport(
        HTTPTransport(
            # Pass a transport with these parameters to wrap.
            http2=True,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=100, keepalive_expiry=60),
            verify=False
        ),
        retry=Retry(total=5, backoff_factor=0.5),
    )
    # These will do nothing!
    http2=True,
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=100, keepalive_expiry=60),
    verify=False
) as client:
    ...
```
