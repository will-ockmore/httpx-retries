# HTTPX Retries


<p>
<a href="https://github.com/will-ockmore/httpx-retry/actions">
    <img src="https://github.com/will-ockmore/httpx-retry/workflows/Test%20Suite/badge.svg" alt="Test Suite">
</a>
<!-- TODO: Enable after package publish -->
<!-- <a href="https://pypi.org/project/httpx/"> -->
<!--     <img src="https://badge.fury.io/py/httpx.svg" alt="Package version"> -->
<!-- </a> -->
</p>

<em>A retry layer for HTTPX.</em>


---

HTTPX Retries is a full implementation of request retry policies for HTTPX.

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

For async usage:
``` python
async with httpx.AsyncClient(transport=RetryTransport()) as client:
    response = await client.get("https://example.com")
```

If you want to use a specific retry strategy, provide a [Retry][httpx_retries.Retry] configuration:

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

To reduce boilerplate, this package includes a transport that works with both sync and async HTTPX clients, so you don't have to explicitly define policies for simple use cases.

HTTPX adds support for asynchronous requests, so the package exposes a new retry utility ([Retry][httpx_retries.Retry]). To make it easy to migrate, the API surface is almost identical, with a few main differences:

- `total` is the only parameter used to configure the number of retries.
- [asleep][httpx_retries.Retry.asleep] is an async implementation of [sleep][httpx_retries.Retry.sleep].
- [backoff_strategy][httpx_retries.Retry.backoff_strategy] can be overridden to customize backoff behavior.
- Some options that are not strictly retry-related are not included (`raise_on_status`, `raise_on_redirect`)

!!! note
    For more information, visit the [API reference](./api.md).

## Acknowledgements

This package builds on the great work done on [HTTPX](https://www.python-httpx.org/), [urllib3](https://urllib3.readthedocs.io/en/stable/) and [requests](https://requests.readthedocs.io/en/latest/).
