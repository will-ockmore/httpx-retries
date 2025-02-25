# HTTPX Retries


<p>
<a href="https://github.com/will-ockmore/httpx-retry/actions">
    <img src="https://github.com/will-ockmore/httpx-retry/workflows/Test%20Suite/badge.svg" alt="Test Suite">
</a>
<a href="https://pypi.org/project/httpx-retries/">
    <img src="https://badge.fury.io/py/httpx-retries.svg" alt="Package version">
</a>
</p>

<!-- badges-end -->

<em>A retry layer for HTTPX.</em>


---

HTTPX Retries implements request retry for [HTTPX](https://www.python-httpx.org/).

It's very common to deal with **flaky** and **unreliable** APIs. When requests fail, your program needs to be able
to retry them.

---

Install HTTPX Retries using pip:

``` bash
pip install httpx-retries
```

---

To get started, add the transport to your client:

``` python
import httpx
from httpx_retries import RetryTransport

with httpx.Client(transport=RetryTransport()) as client:
    response = client.get("https://example.com")
```

Async usage is just as straightforward.

``` python
async with httpx.AsyncClient(transport=RetryTransport()) as client:
    response = await client.get("https://example.com")
```

If you want to use a specific retry strategy, provide a `Retry` configuration:

``` python
from httpx_retries import Retry

retry = Retry(total=5, backoff_factor=0.5)
transport = RetryTransport(retry=retry)

with httpx.Client(transport=transport) as client:
    response = client.get("https://example.com")
```

## Features

HTTPX Retries builds on the patterns users will expect from `urllib` and `requests`. The typical approach has been
to use [urllib3's Retry](https://urllib3.readthedocs.io/en/latest/reference/urllib3.util.html#urllib3.util.Retry)
utility to configure a retry policy. The equivalent code to match the above example using
[requests](https://requests.readthedocs.io/en/latest/) is:

``` python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

retry = Retry(total=5, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)

with requests.Session() as session:
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    response = session.get("https://example.com")
```

To reduce boilerplate, this package includes a transport that works with both sync and async HTTPX Clients, with
sensible defaults for simple use cases.

HTTPX adds support for asynchronous requests, and this package includes a new retry utility that can handle this
behaviour.
To make it easy to migrate, the API surface is almost identical to `Retry` from urllib3, with a few main differences:

- `total` is the only parameter used to configure the number of retries.
- `asleep` is an async implementation of `sleep`.
- `backoff_strategy` can be overridden to customize backoff behavior.
- Some options that are not strictly retry-related are not included (`raise_on_status`, `raise_on_redirect`)

## Contributing

If you want to contribute to the project, check out the [Contributing Guide](https://will-ockmore.github.io/httpx-retries/contributing/).

## Acknowledgements

This package builds on the great work done on [HTTPX](https://www.python-httpx.org/), [urllib3](https://urllib3.readthedocs.io/en/stable/) and [requests](https://requests.readthedocs.io/en/latest/).
