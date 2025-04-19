# Logging

HTTPX Retries follows Python's standard logging conventions, and combined with
[httpx's built in logging](https://www.python-httpx.org/logging/) this means it's
easy to see exactly what is happening when retrying requests.

The example below demonstrates this.

```python

import logging
import httpx
from httpx_retries import RetryTransport, Retry

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG
)

transport = RetryTransport(retry=Retry(total=3, backoff_factor=0.5))

with httpx.Client(transport=transport) as client:
    response = client.get("http://httpstat.us/429")
```

The result on `stdout` is:

```
DEBUG [2025-04-19 23:38:57] httpx_retries.transport - handle_request started request=<Request('GET', 'http://httpstat.us/429')>
DEBUG [2025-04-19 23:38:57] httpcore.connection - connect_tcp.started host='httpstat.us' port=80 local_address=None timeout=5.0 socket_options=None
DEBUG [2025-04-19 23:38:57] httpcore.connection - connect_tcp.complete return_value=<httpcore._backends.sync.SyncStream object at 0x1020d39a0>
DEBUG [2025-04-19 23:38:57] httpcore.http11 - send_request_headers.started request=<Request [b'GET']>
DEBUG [2025-04-19 23:38:57] httpcore.http11 - send_request_headers.complete
DEBUG [2025-04-19 23:38:57] httpcore.http11 - send_request_body.started request=<Request [b'GET']>
DEBUG [2025-04-19 23:38:57] httpcore.http11 - send_request_body.complete
DEBUG [2025-04-19 23:38:57] httpcore.http11 - receive_response_headers.started request=<Request [b'GET']>
DEBUG [2025-04-19 23:38:57] httpcore.http11 - receive_response_headers.complete return_value=(b'HTTP/1.1', 429, b'Too Many Requests', [(b'Content-Length', b'21'), (b'Content-Type', b'text/plain'), (b'Date', b'Sat, 19 Apr 2025 22:38:56 GMT'), (b'Server', b'Kestrel'), (b'Retry-After', b'5'), (b'Set-Cookie', b'ARRAffinity=1c4ce6b282a4edef63e94171500d99e8b18888422937ab7168b9007141be8730;Path=/;HttpOnly;Domain=httpstat.us'), (b'Request-Context', b'appId=cid-v1:3548b0f5-7f75-492f-82bb-b6eb0e864e53')])
DEBUG [2025-04-19 23:38:57] httpx_retries.transport - _retry_operation retrying response=<Response [429 Too Many Requests]> retry=<Retry(total=2, attempts_made=1)>
DEBUG [2025-04-19 23:38:57] httpx_retries.retry - sleep seconds=5.0
DEBUG [2025-04-19 23:39:02] httpcore.connection - connect_tcp.started host='httpstat.us' port=80 local_address=None timeout=5.0 socket_options=None
DEBUG [2025-04-19 23:39:02] httpcore.connection - connect_tcp.complete return_value=<httpcore._backends.sync.SyncStream object at 0x1020ecdc0>
DEBUG [2025-04-19 23:39:02] httpcore.http11 - send_request_headers.started request=<Request [b'GET']>
DEBUG [2025-04-19 23:39:02] httpcore.http11 - send_request_headers.complete
DEBUG [2025-04-19 23:39:02] httpcore.http11 - send_request_body.started request=<Request [b'GET']>
DEBUG [2025-04-19 23:39:02] httpcore.http11 - send_request_body.complete
DEBUG [2025-04-19 23:39:02] httpcore.http11 - receive_response_headers.started request=<Request [b'GET']>
DEBUG [2025-04-19 23:39:03] httpcore.http11 - receive_response_headers.complete return_value=(b'HTTP/1.1', 429, b'Too Many Requests', [(b'Content-Length', b'21'), (b'Content-Type', b'text/plain'), (b'Date', b'Sat, 19 Apr 2025 22:39:02 GMT'), (b'Server', b'Kestrel'), (b'Retry-After', b'5'), (b'Set-Cookie', b'ARRAffinity=1c4ce6b282a4edef63e94171500d99e8b18888422937ab7168b9007141be8730;Path=/;HttpOnly;Domain=httpstat.us'), (b'Request-Context', b'appId=cid-v1:3548b0f5-7f75-492f-82bb-b6eb0e864e53')])
DEBUG [2025-04-19 23:39:03] httpx_retries.transport - _retry_operation retrying response=<Response [429 Too Many Requests]> retry=<Retry(total=2, attempts_made=2)>
DEBUG [2025-04-19 23:39:03] httpx_retries.retry - sleep seconds=5.0
DEBUG [2025-04-19 23:39:08] httpcore.connection - connect_tcp.started host='httpstat.us' port=80 local_address=None timeout=5.0 socket_options=None
DEBUG [2025-04-19 23:39:08] httpcore.connection - connect_tcp.complete return_value=<httpcore._backends.sync.SyncStream object at 0x1020eca30>
DEBUG [2025-04-19 23:39:08] httpcore.http11 - send_request_headers.started request=<Request [b'GET']>
DEBUG [2025-04-19 23:39:08] httpcore.http11 - send_request_headers.complete
DEBUG [2025-04-19 23:39:08] httpcore.http11 - send_request_body.started request=<Request [b'GET']>
DEBUG [2025-04-19 23:39:08] httpcore.http11 - send_request_body.complete
DEBUG [2025-04-19 23:39:08] httpcore.http11 - receive_response_headers.started request=<Request [b'GET']>
DEBUG [2025-04-19 23:39:08] httpcore.http11 - receive_response_headers.complete return_value=(b'HTTP/1.1', 429, b'Too Many Requests', [(b'Content-Length', b'21'), (b'Content-Type', b'text/plain'), (b'Date', b'Sat, 19 Apr 2025 22:39:07 GMT'), (b'Server', b'Kestrel'), (b'Retry-After', b'5'), (b'Set-Cookie', b'ARRAffinity=1c4ce6b282a4edef63e94171500d99e8b18888422937ab7168b9007141be8730;Path=/;HttpOnly;Domain=httpstat.us'), (b'Request-Context', b'appId=cid-v1:3548b0f5-7f75-492f-82bb-b6eb0e864e53')])
DEBUG [2025-04-19 23:39:08] httpx_retries.transport - handle_request finished request=<Request('GET', 'http://httpstat.us/429')> response=<Response [429 Too Many Requests]>
INFO [2025-04-19 23:39:08] httpx - HTTP Request: GET http://httpstat.us/429 "HTTP/1.1 429 Too Many Requests"
DEBUG [2025-04-19 23:39:08] httpcore.http11 - receive_response_body.started request=<Request [b'GET']>
DEBUG [2025-04-19 23:39:08] httpcore.http11 - receive_response_body.complete
DEBUG [2025-04-19 23:39:08] httpcore.http11 - response_closed.started
DEBUG [2025-04-19 23:39:08] httpcore.http11 - response_closed.complete
```
