"""Shared outbound HTTP client — uniform timeout, one retry with jitter on
transient failures (timeout / connection reset / 5xx), and structured log
lines for every attempt."""

import asyncio
import errno
import logging
import random
import time
from collections.abc import Callable
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S: float = 30.0
_RETRY_BACKOFF_MIN_S: float = 0.4
_RETRY_BACKOFF_MAX_S: float = 0.7


class ShortTransfer(OSError):
    """The peer ended a streamed response before the published size."""


class MalformedRange(ValueError):
    """A resumed response did not describe the requested byte range."""


class OperationCancelled(RuntimeError):
    """A caller-requested streaming operation was cancelled."""


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
        delay = random.uniform(_RETRY_BACKOFF_MIN_S, _RETRY_BACKOFF_MAX_S)  # nosec B311 - jitter for HTTP retry, not security-sensitive
        await asyncio.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("http_client.get: exhausted retries without a response")


async def stream_to_file(
    url: str,
    dest: Path,
    *,
    expected_size: int,
    on_bytes: Callable[[int], None],
    cancel: asyncio.Event,
    label: str,
) -> None:
    """Resume a bounded HTTP download into *dest* with one transient retry."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > expected_size:
        dest.unlink()
        raise ValueError("partial download is larger than the published file")
    if dest.exists() and dest.stat().st_size == expected_size:
        on_bytes(expected_size)
        return

    for attempt in (1, 2):
        start = dest.stat().st_size if dest.exists() else 0
        headers = {"Range": f"bytes={start}-"}
        logger.info("[http] %s → %s attempt=%d range=%d-", label, url, attempt, start)
        t0 = time.perf_counter()
        status_code: int | None = None
        try:
            async with httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT_S, follow_redirects=True
            ) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    status_code = response.status_code
                    if response.status_code == 206:
                        expected_range = f"bytes {start}-{expected_size - 1}/{expected_size}"
                        if response.headers.get("Content-Range") != expected_range:
                            raise MalformedRange(
                                "unexpected Content-Range "
                                f"{response.headers.get('Content-Range')!r}; "
                                f"expected {expected_range!r}"
                            )
                        mode = "ab"
                    elif response.status_code == 200:
                        start = 0
                        mode = "wb"
                    else:
                        response.raise_for_status()
                        raise RuntimeError("unreachable")

                    done = start
                    with dest.open(mode) as output:
                        async for chunk in response.aiter_bytes():
                            if cancel.is_set():
                                raise OperationCancelled("operation cancelled")
                            remaining = expected_size - done
                            if remaining <= 0:
                                break
                            bounded = chunk[:remaining]
                            output.write(bounded)
                            done += len(bounded)
                            on_bytes(done)
                            if len(bounded) < len(chunk):
                                break
                    if done < expected_size:
                        raise ShortTransfer(
                            errno.ECONNRESET,
                            f"stream ended at {done} bytes; expected {expected_size}",
                        )
                    logger.info(
                        "[http] %s ← %s in %.0f ms (%d bytes, attempt %d)",
                        label,
                        response.status_code,
                        (time.perf_counter() - t0) * 1000,
                        done - start,
                        attempt,
                    )
                    return
        except asyncio.CancelledError:
            raise
        except OperationCancelled:
            raise
        except MalformedRange:
            raise
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise
            retryable = isinstance(exc, ShortTransfer)
            if attempt == 2 or not retryable:
                raise
        except Exception as exc:
            if attempt == 2 or not _is_retryable(exc, status_code):
                raise
        delay = random.uniform(_RETRY_BACKOFF_MIN_S, _RETRY_BACKOFF_MAX_S)  # nosec B311
        await asyncio.sleep(delay)
