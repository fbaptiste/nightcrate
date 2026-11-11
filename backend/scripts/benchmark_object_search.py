"""Measure the v0.49 object-search speed budget against an isolated workspace."""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from nightcrate.core import app_config
from nightcrate.db.session import set_db_path
from nightcrate.main import app


async def _timed(
    client: AsyncClient, path: str, params: dict, repeats: int
) -> tuple[float, dict | list]:
    samples: list[float] = []
    body: dict | list = {}
    for _ in range(repeats):
        started = time.perf_counter()
        response = await client.get(path, params=params)
        elapsed = (time.perf_counter() - started) * 1000.0
        response.raise_for_status()
        body = response.json()
        samples.append(elapsed)
    return statistics.median(samples), body


async def _run(workspace: Path, repeats: int) -> int:
    database = workspace / app_config.DB_FILENAME if workspace.is_dir() else workspace
    if not database.is_file():
        raise ValueError(f"Workspace database does not exist: {database}")
    set_db_path(database)
    failed = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://benchmark") as client:
        await client.get("/api/gallery")
        for query in ("M 31", "galaxy", "NGC 4438"):
            elapsed, body = await _timed(
                client,
                "/api/gallery",
                {"q": query, "search_images": True, "include_retired": True},
                repeats,
            )
            assert isinstance(body, dict)
            items = body["items"]
            solve_count = sum(item["has_solve"] for item in items)
            hit_count = sum(item["match_in_image"] for item in items)
            matched_objects = sum(
                len(item["solve"]["marks"]) for item in items if item["solve"] is not None
            )
            print(
                f"gallery {query!r}: {elapsed:.1f} ms; "
                f"objects={matched_objects} solves={solve_count} hits={hit_count}"
            )
            failed |= elapsed >= 300.0

        for query in ("NGC 4", "gal"):
            elapsed, body = await _timed(
                client,
                "/api/gallery/suggest",
                {"q": query, "search_images": True, "include_retired": True},
                repeats,
            )
            assert isinstance(body, list)
            print(
                f"suggest {query!r}: {elapsed:.1f} ms; "
                f"objects={len(body)} hits={sum(item['project_count'] for item in body)}"
            )
            failed |= elapsed >= 200.0

        elapsed, body = await _timed(
            client,
            "/api/messier",
            {"location": "none"},
            repeats,
        )
        assert isinstance(body, dict)
        print(
            f"messier: {elapsed:.1f} ms; slots={len(body['slots'])} "
            f"in_solved={body['counts']['in_solved']}"
        )
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats must be positive")
    try:
        return asyncio.run(_run(args.workspace.expanduser().resolve(), args.repeats))
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
