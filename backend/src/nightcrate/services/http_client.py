"""Shared outbound HTTP client.

Every outbound call from NightCrate goes through `get_json()` / `get_text()`
so we have a single place for timeout policy, retry-on-transient, and
structured request logging. Prior to this module each caller rolled its own
httpx dance with inconsistent timeouts and zero retry logic.
"""

import asyncio
import logging
import random
import time

import httpx

logger = logging.getLogger(__name__)

# Uniform 30s cap for all outbound requests. Clear Outside was at 10s before
# which was slightly aggressive; standardising.
DEFAULT_TIMEOUT_S: float = 30.0

# Exactly one retry on transient failures (timeout / connection reset / 5xx),
# with a short jittered backoff. Good enough for intermittent upstream blips
# without turning into a DoS on a genuinely down server.
_RETRY_BACKOFF_MIN_S: float = 0.4
_RETRY_BACKOFF_MAX_S: float = 0.7


def _is_retryable(exc: BaseException | None, status_code: int | None) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)):
        return True
    if status_code is not None and 500 <= status_code < 600:
        return True
    return False


async def get(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    label: str | None = None,
    follow_redirects: bool = False,
) -> httpx.Response:
    """GET a URL with uniform timeout, one-retry-with-jitter on transient
    failure, and structured log lines before/after each attempt.

    Returns the final response object. Non-2xx final responses are returned
    as-is — callers decide whether to raise_for_status() or consume them."""
    label = label or url
    last_exc: BaseException | None = None
    for attempt in (1, 2):
        logger.info(
            "[http] %s → %s attempt=%d%s",
            label,
            url,
            attempt,
            f" params={params}" if params else "",
        )
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=follow_redirects
            ) as client:
                response = await client.get(url, params=params, headers=headers)
        except Exception as exc:
            dt_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "[http] %s ✗ %s after %.0f ms (attempt %d)",
                label,
                type(exc).__name__,
                dt_ms,
                attempt,
            )
            last_exc = exc
            if attempt == 2 or not _is_retryable(exc, None):
                raise
        else:
            dt_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "[http] %s ← %s in %.0f ms (%d bytes, attempt %d)",
                label,
                response.status_code,
                dt_ms,
                len(response.content) if response.content else 0,
                attempt,
            )
            if attempt == 2 or not _is_retryable(None, response.status_code):
                return response
            last_exc = None

        # Jittered backoff before the retry.
        delay = random.uniform(_RETRY_BACKOFF_MIN_S, _RETRY_BACKOFF_MAX_S)
        await asyncio.sleep(delay)

    # Unreachable in practice (loop always returns or raises), but satisfies
    # the type checker and makes the control flow explicit.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("http_client.get: exhausted retries without a response")
