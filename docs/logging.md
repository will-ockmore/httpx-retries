# Logging

HTTPX Retries follows Python's standard logging conventions, and combined with
[httpx's built in logging](https://www.python-httpx.org/logging/) this means it's
easy to see exactly what is happening when retrying requests.

The example below demonstrates this.

```python
import logging

import httpx

from httpx_retries import Retry, RetryTransport

logging.basicConfig(
    format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG
)

transport = RetryTransport(retry=Retry(total=3, backoff_factor=0.5))

with httpx.Client(transport=transport) as client:
    response = client.get("https://httpco.de/429")
```

The result on `stdout` is:

```
DEBUG [2025-08-23 09:34:21] httpx_retries.transport - handle_request started request=<Request('GET', 'https://httpco.de/429')>
DEBUG [2025-08-23 09:34:21] httpcore.connection - connect_tcp.started host='httpco.de' port=443 local_address=None timeout=5.0 socket_options=None
DEBUG [2025-08-23 09:34:21] httpcore.connection - connect_tcp.complete return_value=<httpcore._backends.sync.SyncStream object at 0x1070af9a0>
DEBUG [2025-08-23 09:34:21] httpcore.connection - start_tls.started ssl_context=<ssl.SSLContext object at 0x1070a0510> server_hostname='httpco.de' timeout=5.0
DEBUG [2025-08-23 09:34:22] httpcore.connection - start_tls.complete return_value=<httpcore._backends.sync.SyncStream object at 0x1070af970>
DEBUG [2025-08-23 09:34:22] httpcore.http11 - send_request_headers.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:22] httpcore.http11 - send_request_headers.complete
DEBUG [2025-08-23 09:34:22] httpcore.http11 - send_request_body.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:22] httpcore.http11 - send_request_body.complete
DEBUG [2025-08-23 09:34:22] httpcore.http11 - receive_response_headers.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:22] httpcore.http11 - receive_response_headers.complete return_value=(b'HTTP/1.1', 429, b'Too Many Requests', [(b'Date', b'Sat, 23 Aug 2025 08:34:22 GMT'), (b'Content-Type', b'text/plain; charset=utf-8'), (b'Content-Length', b'17'), (b'Connection', b'keep-alive')])
DEBUG [2025-08-23 09:34:22] httpx_retries.transport - _retry_operation retrying request=<Request('GET', 'https://httpco.de/429')> response=<Response [429 Too Many Requests]> retry=<Retry(total=3, attempts_made=0)>
DEBUG [2025-08-23 09:34:22] httpx_retries.retry - increment retry=<Retry(total=3, attempts_made=0)> new_attempts_made=1
DEBUG [2025-08-23 09:34:22] httpx_retries.retry - sleep seconds=0.7751384536885068
DEBUG [2025-08-23 09:34:22] httpcore.connection - connect_tcp.started host='httpco.de' port=443 local_address=None timeout=5.0 socket_options=None
DEBUG [2025-08-23 09:34:22] httpcore.connection - connect_tcp.complete return_value=<httpcore._backends.sync.SyncStream object at 0x1070c7c40>
DEBUG [2025-08-23 09:34:22] httpcore.connection - start_tls.started ssl_context=<ssl.SSLContext object at 0x1070a0510> server_hostname='httpco.de' timeout=5.0
DEBUG [2025-08-23 09:34:23] httpcore.connection - start_tls.complete return_value=<httpcore._backends.sync.SyncStream object at 0x1070c7c10>
DEBUG [2025-08-23 09:34:23] httpcore.http11 - send_request_headers.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:23] httpcore.http11 - send_request_headers.complete
DEBUG [2025-08-23 09:34:23] httpcore.http11 - send_request_body.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:23] httpcore.http11 - send_request_body.complete
DEBUG [2025-08-23 09:34:23] httpcore.http11 - receive_response_headers.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:23] httpcore.http11 - receive_response_headers.complete return_value=(b'HTTP/1.1', 429, b'Too Many Requests', [(b'Date', b'Sat, 23 Aug 2025 08:34:23 GMT'), (b'Content-Type', b'text/plain; charset=utf-8'), (b'Content-Length', b'17'), (b'Connection', b'keep-alive')])
DEBUG [2025-08-23 09:34:23] httpx_retries.transport - _retry_operation retrying request=<Request('GET', 'https://httpco.de/429')> response=<Response [429 Too Many Requests]> retry=<Retry(total=3, attempts_made=1)>
DEBUG [2025-08-23 09:34:23] httpx_retries.retry - increment retry=<Retry(total=3, attempts_made=1)> new_attempts_made=2
DEBUG [2025-08-23 09:34:23] httpx_retries.retry - sleep seconds=0.979677107701836
DEBUG [2025-08-23 09:34:24] httpcore.connection - connect_tcp.started host='httpco.de' port=443 local_address=None timeout=5.0 socket_options=None
DEBUG [2025-08-23 09:34:24] httpcore.connection - connect_tcp.complete return_value=<httpcore._backends.sync.SyncStream object at 0x1070e54c0>
DEBUG [2025-08-23 09:34:24] httpcore.connection - start_tls.started ssl_context=<ssl.SSLContext object at 0x1070a0510> server_hostname='httpco.de' timeout=5.0
DEBUG [2025-08-23 09:34:24] httpcore.connection - start_tls.complete return_value=<httpcore._backends.sync.SyncStream object at 0x1070c7940>
DEBUG [2025-08-23 09:34:24] httpcore.http11 - send_request_headers.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:24] httpcore.http11 - send_request_headers.complete
DEBUG [2025-08-23 09:34:24] httpcore.http11 - send_request_body.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:24] httpcore.http11 - send_request_body.complete
DEBUG [2025-08-23 09:34:24] httpcore.http11 - receive_response_headers.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:24] httpcore.http11 - receive_response_headers.complete return_value=(b'HTTP/1.1', 429, b'Too Many Requests', [(b'Date', b'Sat, 23 Aug 2025 08:34:24 GMT'), (b'Content-Type', b'text/plain; charset=utf-8'), (b'Content-Length', b'17'), (b'Connection', b'keep-alive')])
DEBUG [2025-08-23 09:34:24] httpx_retries.transport - _retry_operation retrying request=<Request('GET', 'https://httpco.de/429')> response=<Response [429 Too Many Requests]> retry=<Retry(total=3, attempts_made=2)>
DEBUG [2025-08-23 09:34:24] httpx_retries.retry - increment retry=<Retry(total=3, attempts_made=2)> new_attempts_made=3
DEBUG [2025-08-23 09:34:24] httpx_retries.retry - sleep seconds=2.250136320382409
DEBUG [2025-08-23 09:34:26] httpcore.connection - connect_tcp.started host='httpco.de' port=443 local_address=None timeout=5.0 socket_options=None
DEBUG [2025-08-23 09:34:26] httpcore.connection - connect_tcp.complete return_value=<httpcore._backends.sync.SyncStream object at 0x1070e51c0>
DEBUG [2025-08-23 09:34:26] httpcore.connection - start_tls.started ssl_context=<ssl.SSLContext object at 0x1070a0510> server_hostname='httpco.de' timeout=5.0
DEBUG [2025-08-23 09:34:27] httpcore.connection - start_tls.complete return_value=<httpcore._backends.sync.SyncStream object at 0x1070e5430>
DEBUG [2025-08-23 09:34:27] httpcore.http11 - send_request_headers.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:27] httpcore.http11 - send_request_headers.complete
DEBUG [2025-08-23 09:34:27] httpcore.http11 - send_request_body.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:27] httpcore.http11 - send_request_body.complete
DEBUG [2025-08-23 09:34:27] httpcore.http11 - receive_response_headers.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:27] httpcore.http11 - receive_response_headers.complete return_value=(b'HTTP/1.1', 429, b'Too Many Requests', [(b'Date', b'Sat, 23 Aug 2025 08:34:27 GMT'), (b'Content-Type', b'text/plain; charset=utf-8'), (b'Content-Length', b'17'), (b'Connection', b'keep-alive')])
DEBUG [2025-08-23 09:34:27] httpx_retries.transport - handle_request finished request=<Request('GET', 'https://httpco.de/429')> response=<Response [429 Too Many Requests]>
INFO [2025-08-23 09:34:27] httpx - HTTP Request: GET https://httpco.de/429 "HTTP/1.1 429 Too Many Requests"
DEBUG [2025-08-23 09:34:27] httpcore.http11 - receive_response_body.started request=<Request [b'GET']>
DEBUG [2025-08-23 09:34:27] httpcore.http11 - receive_response_body.complete
DEBUG [2025-08-23 09:34:27] httpcore.http11 - response_closed.started
DEBUG [2025-08-23 09:34:27] httpcore.http11 - response_closed.complete
```
