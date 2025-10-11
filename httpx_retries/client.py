import logging
import typing
from typing import Optional

import httpx
from httpx import BaseTransport, HTTPTransport
from httpx._client import EventHook
from httpx._config import (
    DEFAULT_LIMITS,
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_TIMEOUT_CONFIG,
    Limits,
)
from httpx._types import (
    AuthTypes,
    CertTypes,
    CookieTypes,
    HeaderTypes,
    ProxyTypes,
    QueryParamTypes,
    TimeoutTypes,
)
from httpx._urls import URL

if typing.TYPE_CHECKING:
    import ssl  # pragma: no cover

from .retry import Retry as Retry
from .transport import RetryTransport

logger = logging.getLogger(__name__)


class RetryClient(httpx.Client):
    """
    A client that automatically retries failed requests.

    ```python
    with RetryClient() as client:
        response = client.get("https://example.com")

    async with httpx.AsyncClient() as client:
        response = await client.get("https://example.com")
    ```

    If you want to use a specific retry strategy, provide a [Retry][httpx_retries.Retry] configuration:

    ```python
    retry = Retry(total=5, backoff_factor=0.5)

    with RetryClient(retry=retry) as client:
        response = client.get("https://example.com")
    ```
    """

    def __init__(
        self,
        *,
        auth: AuthTypes | None = None,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        verify: ssl.SSLContext | str | bool = True,
        cert: CertTypes | None = None,
        trust_env: bool = True,
        http1: bool = True,
        http2: bool = False,
        proxy: ProxyTypes | None = None,
        mounts: None | (typing.Mapping[str, BaseTransport | None]) = None,
        timeout: TimeoutTypes = DEFAULT_TIMEOUT_CONFIG,
        follow_redirects: bool = False,
        limits: Limits = DEFAULT_LIMITS,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        event_hooks: None | (typing.Mapping[str, list[EventHook]]) = None,
        base_url: URL | str = "",
        transport: Optional[BaseTransport] = None,
        default_encoding: str | typing.Callable[[bytes], str] = "utf-8",
        retry: Optional[Retry] = None,
    ) -> None:
        self._retry = retry or Retry()

        super().__init__(
            auth=auth,
            params=params,
            headers=headers,
            cookies=cookies,
            verify=verify,
            cert=cert,
            trust_env=trust_env,
            http1=http1,
            http2=http2,
            proxy=proxy,
            mounts=mounts,
            timeout=timeout,
            follow_redirects=follow_redirects,
            limits=limits,
            max_redirects=max_redirects,
            event_hooks=event_hooks,
            base_url=base_url,
            transport=transport,
            default_encoding=default_encoding,
        )

    def _init_transport(
        self,
        verify: ssl.SSLContext | str | bool = True,
        cert: CertTypes | None = None,
        trust_env: bool = True,
        http1: bool = True,
        http2: bool = False,
        limits: Limits = DEFAULT_LIMITS,
        transport: BaseTransport | None = None,
    ) -> BaseTransport:
        if transport is not None:
            return transport

        return RetryTransport(
            HTTPTransport(
                verify=verify,
                cert=cert,
                trust_env=trust_env,
                http1=http1,
                http2=http2,
                limits=limits,
            ),
            retry=self._retry,
        )
