import logging

import httpx

from httpx_retries import Retry, RetryTransport

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S", level=logging.DEBUG
)

transport = RetryTransport(retry=Retry(total=2))

with httpx.Client(transport=transport) as client:
    response = client.get("http://httpstat.us/429")
