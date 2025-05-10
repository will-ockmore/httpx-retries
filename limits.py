# ruff: noqa

import httpx

from httpx_retries import Retry, RetryTransport

retries = Retry(
    total=3,
    backoff_factor=0.2,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS"],
)

transport = RetryTransport(retry=retries)
session = httpx.Client(
    transport=transport,
    http2=True,
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=100, keepalive_expiry=60),
    headers={
        "User-Agent": f"Python/{__version__}",
        "Content-Type": "application/json",
    },
)
return session
