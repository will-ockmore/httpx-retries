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

It's very common to deal with **flaky** and **unreliable** APIs. When requests fail, applications need to be able
to resend them.

---

Install HTTPX Retries using pip:

``` bash
pip install httpx-retries
```

---

To get started, define your retry strategy and add the transport to your client.

``` python
import httpx
from httpx_retries import Retry, RetryTransport

retry = Retry(total=5, backoff_factor=0.5, respect_retry_after_header=False)
transport = RetryTransport(retry=retry)

with httpx.Client(transport=transport) as client:
    response = client.get("https://example.com")
```

## Features

HTTPX Retries builds on the patterns users will expect from `urllib` and `requests`. The typical approach has been
to use [urllib3's Retry](https://urllib3.readthedocs.io/en/latest/reference/urllib3.util.html#urllib3.util.Retry)
utility to configure a retry policy. For example, with [requests](https://requests.readthedocs.io/en/latest/) the above
code becomes

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

To reduce boilerplate, this package includes custom transports
 ([RetryTransport][httpx_retries.RetryTransport] and [AsyncRetryTransport][httpx_retries.AsyncRetryTransport]), so
you don't have to to explicitly define policies for simple use cases.

As HTTPX adds support for asynchronous requests, the package exposes a new retry
utility ([Retry][httpx_retries.Retry]). To make it easy to migrate, the API surface is almost identical, with a few main
differences:

- `total` is the only parameter used to configure the number of retries.
- [asleep][httpx_retries.Retry.asleep] is an async implementation of [sleep][httpx_retries.Retry.sleep].
- [backoff_strategy][httpx_retries.Retry.backoff_strategy] can be overridden to customize backoff behavior.
