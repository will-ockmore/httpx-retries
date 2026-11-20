import anyio
import httpx
import pytest

from httpx_retries import Retry, RetryTransport


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["status", "exception", "validation"])
@pytest.mark.parametrize("backoff_factor", [0.0, 0.001])
async def test_retry_transport_on_anyio_backend(failure: str, backoff_factor: float) -> None:
    calls: list[httpx.Request] = []
    responses: list[httpx.Response] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1 and failure == "exception":
            raise httpx.ConnectError("temporary failure", request=request)
        response = httpx.Response(503 if len(calls) == 1 and failure == "status" else 200)
        responses.append(response)
        return response

    def validate(response: httpx.Response) -> None:
        if len(calls) == 1 and failure == "validation":
            raise httpx.ReadError("temporary validation failure", request=response.request)

    retry = Retry(total=1, backoff_factor=backoff_factor, backoff_jitter=0, validate_response=validate)
    transport = RetryTransport(transport=httpx.MockTransport(handler), retry=retry)
    with anyio.fail_after(1):
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.get("https://example.org/")

    assert response.status_code == 200
    assert len(calls) == 2
    assert response.extensions["retry"].attempts_made == 1
    assert response.extensions["retry"].elapsed_sleep == 2 * backoff_factor
    assert all(previous.is_closed for previous in responses)
    assert retry.attempts_made == 0
    assert retry.elapsed_sleep == 0


@pytest.mark.anyio
async def test_retry_sleep_cancellation_on_anyio_backend() -> None:
    retry = Retry(total=1, attempts_made=1)
    response = httpx.Response(503, headers={"Retry-After": "10"})
    with anyio.move_on_after(0.01) as scope:
        await retry.asleep(response)

    assert scope.cancel_called
    assert retry.elapsed_sleep == 0
