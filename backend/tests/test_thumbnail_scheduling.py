from __future__ import annotations

import asyncio

import pytest

from nightcrate.db.session import get_db
from nightcrate.services import hips_tiles, thumbnails

_FAKE_JPEG = b"\xff\xd8" + b"scheduled-thumbnail" * 200


async def _start_waiter(
    gate: thumbnails._MostRecentRequestGate,
    name: str,
    entered: list[str],
    started: asyncio.Event,
    release: asyncio.Event,
) -> None:
    async with gate.slot(name):
        entered.append(name)
        started.set()
        await release.wait()


async def test_gate_admits_waiters_most_recently_requested_first():
    gate = thumbnails._MostRecentRequestGate(1)
    entered: list[str] = []
    started = {name: asyncio.Event() for name in ("holder", "A", "B", "C")}
    release = {name: asyncio.Event() for name in ("holder", "A", "B", "C")}

    tasks = [
        asyncio.create_task(
            _start_waiter(gate, "holder", entered, started["holder"], release["holder"])
        )
    ]
    await started["holder"].wait()
    for name in ("A", "B", "C"):
        tasks.append(
            asyncio.create_task(_start_waiter(gate, name, entered, started[name], release[name]))
        )
        await asyncio.sleep(0)

    release["holder"].set()
    for name in ("C", "B", "A"):
        await asyncio.wait_for(started[name].wait(), 1)
        release[name].set()
    await asyncio.gather(*tasks)

    assert entered == ["holder", "C", "B", "A"]
    assert gate.active_count == 0
    assert gate.waiting_count == 0


async def test_touch_moves_an_older_waiter_to_the_front():
    gate = thumbnails._MostRecentRequestGate(1)
    entered: list[str] = []
    started = {name: asyncio.Event() for name in ("holder", "A", "B", "C")}
    release = {name: asyncio.Event() for name in ("holder", "A", "B", "C")}

    tasks = [
        asyncio.create_task(
            _start_waiter(gate, "holder", entered, started["holder"], release["holder"])
        )
    ]
    await started["holder"].wait()
    for name in ("A", "B", "C"):
        tasks.append(
            asyncio.create_task(_start_waiter(gate, name, entered, started[name], release[name]))
        )
        await asyncio.sleep(0)
    gate.touch("A")

    release["holder"].set()
    for name in ("A", "C", "B"):
        await asyncio.wait_for(started[name].wait(), 1)
        release[name].set()
    await asyncio.gather(*tasks)

    assert entered == ["holder", "A", "C", "B"]


async def test_cancelled_waiter_leaves_no_trace_or_slot_change():
    gate = thumbnails._MostRecentRequestGate(1)
    entered: list[str] = []
    holder_started = asyncio.Event()
    holder_release = asyncio.Event()
    holder = asyncio.create_task(
        _start_waiter(gate, "holder", entered, holder_started, holder_release)
    )
    await holder_started.wait()

    waiter = asyncio.create_task(
        _start_waiter(gate, "cancelled", entered, asyncio.Event(), asyncio.Event())
    )
    await asyncio.sleep(0)
    assert gate.active_count == 1
    assert gate.waiting_count == 1

    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert gate.active_count == 1
    assert gate.waiting_count == 0

    holder_release.set()
    await holder
    assert gate.active_count == 0


async def test_exception_inside_admitted_work_releases_slot():
    gate = thumbnails._MostRecentRequestGate(1)

    with pytest.raises(RuntimeError, match="render failed"):
        async with gate.slot("broken"):
            raise RuntimeError("render failed")

    assert gate.active_count == 0
    async with gate.slot("next"):
        assert gate.active_count == 1
    assert gate.active_count == 0


async def test_old_task_callback_does_not_abandon_new_entry_for_same_key():
    gate = thumbnails._MostRecentRequestGate(1)
    old_entry = gate.schedule("same-key")
    async with gate.slot("same-key"):
        pass

    asyncio.get_running_loop().call_soon(gate.abandon, old_entry)
    new_entry = gate.schedule("same-key")
    await asyncio.sleep(0)

    assert gate._entries["same-key"] is new_entry
    assert gate.active_count == 1
    gate.abandon(new_entry)
    assert gate.active_count == 0


async def _seed_dso(dso_id: int, ra_deg: float) -> None:
    async with get_db() as conn:
        await conn.execute(
            """
            INSERT OR IGNORE INTO dso_catalog_source
                (source_id, category, display_name, file_path, file_hash)
            VALUES ('scheduling-test', 'nightcrate', 'Scheduling', '/synthetic', 'hash')
            """
        )
        source = await (
            await conn.execute(
                "SELECT id FROM dso_catalog_source WHERE source_id = 'scheduling-test'"
            )
        ).fetchone()
        await conn.execute(
            """
            INSERT INTO dso (
                id, primary_designation, obj_type, ra_deg, dec_deg,
                source_catalog_id, source_row_hash
            ) VALUES (?, ?, 'G', ?, 0, ?, ?)
            """,
            (dso_id, f"TEST-{dso_id}", ra_deg, source["id"], f"row-{dso_id}"),
        )
        await conn.commit()


async def test_second_request_for_in_flight_key_refreshes_render_priority(monkeypatch):
    for dso_id, ra_deg in ((901, 1.0), (902, 2.0), (903, 3.0)):
        await _seed_dso(dso_id, ra_deg)

    gate = thumbnails._MostRecentRequestGate(1)
    monkeypatch.setattr(thumbnails, "_fetch_gate", gate)
    started: list[int] = []
    render_started = {ra: asyncio.Event() for ra in (1, 2, 3)}
    render_release = {ra: asyncio.Event() for ra in (1, 2, 3)}

    async def render(wcs, width, height):
        del width, height
        ra = round(float(wcs.wcs.crval[0]))
        started.append(ra)
        render_started[ra].set()
        await render_release[ra].wait()
        return hips_tiles.RenderedImage(_FAKE_JPEG, frozenset({"test"}))

    monkeypatch.setattr(hips_tiles, "render", render)

    async def request(dso_id: int, ra_deg: float):
        async with get_db() as conn:
            return await thumbnails.get_thumbnail(
                conn,
                dso_id=dso_id,
                variant="list",
                ra_deg=ra_deg,
                dec_deg=0,
                maj_axis_arcmin=5,
                max_cache_bytes=10 * 1024 * 1024,
                conn_factory=get_db,
            )

    try:
        assert (await request(901, 1)).status == "placeholder"
        await render_started[1].wait()
        assert (await request(902, 2)).status == "placeholder"
        assert (await request(903, 3)).status == "placeholder"
        assert (await request(902, 2)).status == "placeholder"

        tasks = list(thumbnails._in_flight.values())
        render_release[1].set()
        await asyncio.wait_for(render_started[2].wait(), 1)
        assert started == [1, 2]
        render_release[2].set()
        await asyncio.wait_for(render_started[3].wait(), 1)
        render_release[3].set()
        await asyncio.gather(*tasks)
    finally:
        for event in render_release.values():
            event.set()
        remaining = list(thumbnails._in_flight.values())
        if remaining:
            await asyncio.gather(*remaining, return_exceptions=True)

    assert started == [1, 2, 3]
    assert gate.active_count == 0
    assert gate.waiting_count == 0
