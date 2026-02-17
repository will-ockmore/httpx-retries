# Differences with other retry libraries

HTTPX Retries tries to make configuring retries simple and centralised.

Other retry libraries commonly used for retrying requests are general purpose, and this typically means the
structure of how you make requests must change if you want to abstract the retry behaviour. This means you've got
another level of abstraction to maintain.

[Tenacity](https://github.com/jd/tenacity) is a popular general-purpose retry library. You wrap a function with a
decorator and that function will be retried if certain conditions are met; you configure these conditions at the
function definition.

If you wanted to retry on connection errors, up to three times, and log a `WARNING` level log each time,
you'd do something like

```python
import logging

import httpx
from tenacity import before_sleep_log, retry, retry_if_exception, stop_after_attempt

logger = logging.getLogger(__name__)

SOME_HOST: str = "..."  # GET requests are known to be flaky on this host.

def is_some_host_predicate(exc: BaseException) -> bool:
    return isinstance(exc, httpx.ConnectError) and exc.request.url.host == SOME_HOST

@retry(
    retry=retry_if_exception(is_some_host_predicate),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    stop=stop_after_attempt(3),
)
async def get_from_some_host(client: httpx.AsyncClient, ...):
    ...
```

There are some disadvantages to this approach:

1. It's less concise. You have to wrap the call to `client.get` with a function and a decorator, and you have to
do this every time you make a request.
2. It incurs a performance cost. The additional function call and any custom predicate logic are not free.
3. It's harder to test. You can use dependency injection with a client-based approach, and test your business logic
without retries if desired.
4. Everything is explicit. You can't rely on sensible defaults.

That's why HTTPX Retries was built; you can avoid the additional overhead unless you need it. It's still possible to
implement fully custom retry strategies, but the common approach should be simple and configured once.
