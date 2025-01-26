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

<em>A modern retry layer for HTTPX.</em>


---

HTTPX Retries is a complete implementation of request retry policies for HTTPX.

It's very common to deal with *flaky* and *unreliable* APIs. When requests fail, applications need the
ability to resend them.

---

Install HTTPX Retries using pip:

```
pip install httpx-retries
```

---

To get started, define your retry strategy and add your transport to your client.

``` python
retry = Retry(total=5, backoff_factor=0.5, respect_retry_after_header=False)
transport = RetryTransport(retry=retry)

with httpx.Client(transport=transport) as client:
    response = client.get("https://example.com")
```


This package includes a custom transport ([RetryTransport][httpx_retries.RetryTransport]) and a retry utility ([Retry][httpx_retries.Retry]), which will be familiar to users of
[urllib3's Retry](https://urllib3.readthedocs.io/en/latest/reference/urllib3.util.html#urllib3.util.Retry).



## Commands

- `mkdocs new [dir-name]` - Create a new project.
- `mkdocs serve` - Start the live-reloading docs server.
- `mkdocs build` - Build the documentation site.
- `mkdocs -h` - Print help message and exit.

## Project layout

    mkdocs.yml    # The configuration file.
    docs/
        index.md  # The documentation homepage.
        ...       # Other markdown pages, images and other files.
