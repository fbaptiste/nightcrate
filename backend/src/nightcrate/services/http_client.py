"""Shared outbound HTTP client — uniform timeout, one retry with jitter on
transient failures (timeout / connection reset / 5xx), and structured log
lines for every attempt."""

import asyncio
import errno
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S: float = 30.0
_RETRY_BACKOFF_MIN_S: float = 0.4
_RETRY_BACKOFF_MAX_S: float = 0.7


@dataclass(frozen=True, slots=True)
class GetEvent:
    """One observable step from an opt-in streaming ``get`` call."""

    kind: Literal["attempt", "response", "bytes", "retry_delay"]
    attempt: int
    status_code: int | None = None
    content_length: int | None = None
    bytes_received: int = 0
    delay_s: float | None = None


class ShortTransfer(OSError):
    """The peer ended a streamed response before the published size."""


class MalformedRange(ValueError):
    """A resumed response did not describe the requested byte range."""


class RangeNotHonoured(RuntimeError):
    """The peer did not serve the exact byte range requested by a piece."""


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
    connect_timeout: float | None = None,
    attempts: int = 2,
    label: str | None = None,
    follow_redirects: bool = False,
    on_event: Callable[[GetEvent], None] | None = None,
) -> httpx.Response:
    """GET a URL with uniform timeout, one-retry-with-jitter on transient
    failure, and structured log lines before/after each attempt.

    ``connect_timeout`` caps connection setup separately from ``timeout``, so
    an unreachable host fails fast while a slow transfer keeps its budget.

    Returns the final response object. Non-2xx final responses are returned
    as-is — callers decide whether to raise_for_status() or consume them."""
    label = label or url
    client_timeout: float | httpx.Timeout = (
        timeout if connect_timeout is None else httpx.Timeout(timeout, connect=connect_timeout)
    )
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        if on_event is not None:
            on_event(GetEvent(kind="attempt", attempt=attempt))
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
                timeout=client_timeout, follow_redirects=follow_redirects
            ) as client:
                if on_event is None:
                    response = await client.get(url, params=params, headers=headers)
                else:
                    async with client.stream(
                        "GET", url, params=params, headers=headers
                    ) as response:
                        raw_length = response.headers.get("Content-Length")
                        try:
                            content_length = int(raw_length) if raw_length is not None else None
                        except ValueError:
                            content_length = None
                        if content_length is not None and content_length < 0:
                            content_length = None
                        on_event(
                            GetEvent(
                                kind="response",
                                attempt=attempt,
                                status_code=response.status_code,
                                content_length=content_length,
                            )
                        )
                        chunks: list[bytes] = []
                        decoded_received = 0
                        async for chunk in response.aiter_bytes():
                            chunks.append(chunk)
                            decoded_received += len(chunk)
                            # Mock transports may supply an already-buffered
                            # response, in which case httpx has no raw-stream
                            # counter. Its buffered bytes are necessarily the
                            # transfer bytes; real streamed responses use the
                            # wire counter, including compressed bodies.
                            wire_received = response.num_bytes_downloaded or decoded_received
                            on_event(
                                GetEvent(
                                    kind="bytes",
                                    attempt=attempt,
                                    status_code=response.status_code,
                                    content_length=content_length,
                                    bytes_received=wire_received,
                                )
                            )
                        # ``aiter_bytes`` deliberately leaves a streamed response
                        # marked unread. Populate the same decoded body that
                        # ``Response.aread`` would expose so callers retain the
                        # normal content/text/json interface after the client closes.
                        response._content = b"".join(chunks)  # noqa: SLF001
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
            if attempt == attempts or not _is_retryable(exc, None):
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
            if attempt == attempts or not _is_retryable(None, response.status_code):
                return response
            last_exc = None

        # Jittered backoff before the retry.
        delay = random.uniform(_RETRY_BACKOFF_MIN_S, _RETRY_BACKOFF_MAX_S)  # nosec B311 - jitter for HTTP retry, not security-sensitive
        if on_event is not None:
            on_event(GetEvent(kind="retry_delay", attempt=attempt, delay_s=delay))
        await asyncio.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("http_client.get: exhausted retries without a response")


async def stream_to_file(
    url: str,
    dest: Path,
    *,
    expected_size: int,
    offset: int = 0,
    total_size: int | None = None,
    allow_whole_file: bool = True,
    on_bytes: Callable[[int], None],
    cancel: asyncio.Event,
    label: str,
) -> None:
    """Resume a bounded HTTP download into *dest* with one transient retry."""
    if expected_size < 0 or offset < 0:
        raise ValueError("offset and expected_size must be non-negative")
    if total_size is not None and offset + expected_size > total_size:
        raise ValueError("requested range extends past total_size")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > expected_size:
        dest.unlink()
        raise ValueError("partial download is larger than the published file")
    if dest.exists() and dest.stat().st_size == expected_size:
        on_bytes(expected_size)
        return

    for attempt in (1, 2):
        have = dest.stat().st_size if dest.exists() else 0
        range_start = offset + have
        range_end = offset + expected_size - 1
        headers = {"Range": f"bytes={range_start}-{range_end}"}
        logger.info(
            "[http] %s → %s attempt=%d range=%d-%d",
            label,
            url,
            attempt,
            range_start,
            range_end,
        )
        t0 = time.perf_counter()
        status_code: int | None = None
        try:
            async with httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT_S, follow_redirects=True
            ) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    status_code = response.status_code
                    if response.status_code == 206:
                        full_size = total_size if total_size is not None else expected_size
                        expected_range = f"bytes {range_start}-{range_end}/{full_size}"
                        if response.headers.get("Content-Range") != expected_range:
                            error = RangeNotHonoured if not allow_whole_file else MalformedRange
                            raise error(
                                "unexpected Content-Range "
                                f"{response.headers.get('Content-Range')!r}; "
                                f"expected {expected_range!r}"
                            )
                        mode = "ab"
                    elif response.status_code == 200:
                        if offset != 0 or not allow_whole_file:
                            raise RangeNotHonoured(
                                f"server returned 200 for requested range {range_start}-{range_end}"
                            )
                        have = 0
                        mode = "wb"
                    else:
                        response.raise_for_status()
                        raise RuntimeError("unreachable")

                    done = have
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
                        done - have,
                        attempt,
                    )
                    return
        except asyncio.CancelledError:
            raise
        except OperationCancelled:
            raise
        except RangeNotHonoured:
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
