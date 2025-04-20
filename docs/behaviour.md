# Retry Behaviour

<p align="center" style="margin: 0 0 10px">
  <img width="350" height="208" src="https://raw.githubusercontent.com/will-ockmore/httpx-retries/master/docs/img/mario_game_over.png" alt='HTTPX'>
</p>

If you haven't seen them before, it's not immedately clear what terms like _exponential backoff_ and _jitter_  mean. And what exactly is a "retry strategy", anyway? In this guide we'll break down each of these concepts, show why the defaults have been chosen, and explain how you can configure a custom approach for your retries.

## Motivation

When clients try to perform operations against a remote server, they don't know

* If they will succeed (whether or not the operation will transiently _fail_)
* If there are other clients also trying to access resources (this is called _contention_)

By configuring their retry behaviour, they can minimise the time and work needed to complete their (and other clients') operation(s).

## Definitions

* **Retry strategy**: The choice on how a series of retries is executed.
  The wait between each retry is the typical output of a retry strategy.
  This may depend on how many retries have already been executed, and if
  the server has provided a `Retry-After` header.
* **Backoff**: When there is backoff, a client will wait for increasingly long periods
  between retries (it "backs off" on retrying). **Exponential backoff** just means that the
  increase in these periods follows an exponential function: typically `2 ** number_of_attempts`.
* **Jitter**: A random factor applied after the backoff is calculated; this serves to
  reduce the wait between retries.

## The default behaviour

By default, the [Retry][httpx_retries.Retry] object will retry immediately on each attempt (unless a `Retry-After` header is received), up to `Retry.total` times.
This is a very simple strategy. It's what most users will expect, which is why it's the default.

It makes the client more resilient to failures, but it also risks contention on the server, if several clients are retrying at the same time.
If there are N clients retrying for the same resource,the work done by server increases proportionally to `N^2`, as `N` clients retry in first round, `N-1` in second and so on.

## Exponential backoff

**Exponential backoff** is a common strategy to avoid this. By spreading the retries over a longer period of time, it aims to make sure the server doesn't become overloaded.

The formula for exponential backoff looks like

```python
backoff_time = backoff_factor * (2 ** attempts_made)
```


!!! info

    On the first attempt, `(exponent ** attempts_made) == 1`, and `backoff_time` will be equal to the `backoff_factor`.


However, if the clients are all retrying at the same time (because they are all following the same exponential wait times), contention is still just as much of an issue, and the amount of work isn't reduced by much (only by the network variance).


To solve the problem of grouped retries, we can use **jitter** to pick a time between some minimum and the exponential backoff time. As this is a random factor, this spreads the retries of the clients evenly, and the server gets a less spiky load. **Full jitter** just means that the range that is randomly picked from is between `0` and `exponential_backoff_time`.

This strategy, known as **Exponential backoff with full jitter**[^1], is optimal when writing a client that might have multiple instances out in the wild.

To enable this strategy, just set the **backoff_factor** parameter for [Retry][httpx_retries.Retry].


!!! tip

    For production usage in clients, it's **highly recommended** to enable this behaviour!

!!! note

    Take some time to read the parameters to [Retry][httpx_retries.Retry], to see what's available to tweak; for example, you can change the amount of `jitter` applied.

## Configuring a custom strategy

If you want to implement your own retry strategy, you can subclass [Retry][httpx_retries.Retry] and override the [backoff_strategy][httpx_retries.Retry.backoff_strategy] method.
This method is called for each retry attempt. Take a look at the [source](https://github.com/will-ockmore/httpx-retries/blob/main/httpx_retries/retry.py) for more information on available attributes and how it's used.

??? example
    If you wanted to wait 1 second for every third attempt, and otherwise use the default strategy:

    ```python
    class CustomRetry(Retry):
        def backoff_strategy(self) -> float:
            if self.attempts_made % 3:
                return 1.0

            return super().backoff_strategy()
    ```





[^1]: A great resource for this topic, with some wonderful graphs, can be found on Amazon's architecture blog: [Exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
