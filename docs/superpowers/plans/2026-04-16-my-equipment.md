# My Equipment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-row `is_mine` flag to 10 equipment tables, a dedicated "My Equipment" sidebar section, a clickable star toggle in equipment lists, and a "My Equipment" virtual group at the top of rig-builder dropdowns.

**Architecture:** Boolean column + partial index on each of 10 equipment tables (edited in place in migration 0005). Existing list endpoints gain `?mine=true` filter and `ORDER BY is_mine DESC` default ordering. Two new endpoints: per-type `POST /<type>/{id}/mine` toggle and `GET /equipment/mine-counts` for sidebar rendering. Frontend adds: a shared star column in `EquipmentList`, a shared `MineCheckbox` used in all 10 form dialogs, a new "MY EQUIPMENT" sidebar group with reactive sub-items, and custom `groupBy`/`renderOption` in every rig-builder Autocomplete.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, aiosqlite, yoyo-migrations, pytest. React 18, TypeScript, MUI, MUI X DataGrid, TanStack Query, Vite.

**Spec reference:** `docs/superpowers/specs/2026-04-16-my-equipment-design.md`

**Pre-release note:** Fred will recreate the DB from scratch after schema changes; no ALTER TABLE migrations needed.

---

## Task 1: Schema — add `is_mine` column + partial index to 10 equipment tables

**Files:**
- Modify: `backend/src/nightcrate/db/migrations/0005.equipment_schema.sql`

The column is inserted into each `CREATE TABLE` body before the seed-tracking columns (which start with `created_at` / `updated_at`). Place it directly before `created_at` for each of the 10 tables.

- [ ] **Step 1: Add `is_mine` column and partial index to the `camera` table**

In `backend/src/nightcrate/db/migrations/0005.equipment_schema.sql`, locate the `CREATE TABLE IF NOT EXISTS camera (...)` block (around line 266). Inside the column list, before the `created_at` line, insert:

```sql
  is_mine INTEGER NOT NULL DEFAULT 0 CHECK(is_mine IN (0, 1)),
```

Then, after the table's closing `);`, and before any existing indexes for that table, add:

```sql
CREATE INDEX IF NOT EXISTS idx_camera_mine ON camera(is_mine) WHERE is_mine = 1;
```

- [ ] **Step 2: Apply the same change to the 9 remaining equipment tables**

Repeat Step 1 for each table below. For each, add the identical column line before `created_at`, and add the matching partial index after the `CREATE TABLE` statement:

| Table | Index statement |
|---|---|
| `telescope` | `CREATE INDEX IF NOT EXISTS idx_telescope_mine ON telescope(is_mine) WHERE is_mine = 1;` |
| `filter` | `CREATE INDEX IF NOT EXISTS idx_filter_mine ON filter(is_mine) WHERE is_mine = 1;` |
| `mount` | `CREATE INDEX IF NOT EXISTS idx_mount_mine ON mount(is_mine) WHERE is_mine = 1;` |
| `focuser` | `CREATE INDEX IF NOT EXISTS idx_focuser_mine ON focuser(is_mine) WHERE is_mine = 1;` |
| `filter_wheel` | `CREATE INDEX IF NOT EXISTS idx_filter_wheel_mine ON filter_wheel(is_mine) WHERE is_mine = 1;` |
| `oag` | `CREATE INDEX IF NOT EXISTS idx_oag_mine ON oag(is_mine) WHERE is_mine = 1;` |
| `guide_scope` | `CREATE INDEX IF NOT EXISTS idx_guide_scope_mine ON guide_scope(is_mine) WHERE is_mine = 1;` |
| `computer` | `CREATE INDEX IF NOT EXISTS idx_computer_mine ON computer(is_mine) WHERE is_mine = 1;` |
| `software` | `CREATE INDEX IF NOT EXISTS idx_software_mine ON software(is_mine) WHERE is_mine = 1;` |

Do **not** add `is_mine` to: `sensor`, `telescope_configuration`, any junction table (`*_interface`, `telescope_connector`), any child table (`filter_passband`, `filter_size_option`), any lookup table, or the alias tables.

- [ ] **Step 3: Delete the existing test database and re-run migrations**

Run from `backend/`:

```bash
rm -f ~/Library/Application\ Support/NightCrate/nightcrate.db
uv run python -c "
import asyncio
from nightcrate.db.migrations import apply_migrations
from nightcrate.core.app_config import get_active_db_path
apply_migrations(get_active_db_path())
print('migrations applied')
"
```

Expected: `migrations applied`, no errors.

(If Fred's active DB path differs, substitute the actual path. If none configured, skip this step and let the test suite re-create a fresh DB.)

- [ ] **Step 4: Write a test that verifies `is_mine` exists on all 10 tables**

Create `backend/tests/test_mine_schema.py`:

```python
"""Schema regression: ensure is_mine column exists on owned equipment tables."""
import pytest

OWNED_TABLES = [
    "camera", "telescope", "filter", "mount", "focuser",
    "filter_wheel", "oag", "guide_scope", "computer", "software",
]

NOT_OWNED_TABLES = [
    "sensor", "telescope_configuration", "manufacturer",
    "optical_design", "filter_type",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("table", OWNED_TABLES)
async def test_is_mine_column_exists(test_db, table):
    async with test_db as conn:
        rows = await conn.execute(f"PRAGMA table_info({table})")
        cols = {r[1]: r for r in await rows.fetchall()}
        assert "is_mine" in cols, f"{table} missing is_mine column"
        info = cols["is_mine"]
        # cid, name, type, notnull, dflt_value, pk
        assert info[2] == "INTEGER", f"{table}.is_mine wrong type"
        assert info[3] == 1, f"{table}.is_mine should be NOT NULL"
        assert info[4] == "0", f"{table}.is_mine should default to 0"


@pytest.mark.asyncio
@pytest.mark.parametrize("table", NOT_OWNED_TABLES)
async def test_is_mine_not_on_non_owned_tables(test_db, table):
    async with test_db as conn:
        rows = await conn.execute(f"PRAGMA table_info({table})")
        cols = {r[1] for r in await rows.fetchall()}
        assert "is_mine" not in cols, f"{table} should not have is_mine"


@pytest.mark.asyncio
@pytest.mark.parametrize("table", OWNED_TABLES)
async def test_is_mine_partial_index_exists(test_db, table):
    async with test_db as conn:
        rows = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
            (table,),
        )
        index_names = {r[0] for r in await rows.fetchall()}
        assert f"idx_{table}_mine" in index_names, (
            f"missing partial mine index on {table}"
        )
```

Note: if the project's test fixtures don't already expose a `test_db` async context manager, look at `backend/tests/conftest.py` for the existing DB fixture name and replace `test_db` with it. The codebase already has tests that open DB connections in `test_equipment_schema.py` — use the same pattern.

- [ ] **Step 5: Run the schema test and verify it passes**

Run: `cd backend && uv run pytest tests/test_mine_schema.py -v`

Expected: all 25 tests pass (10 owned + 5 not-owned + 10 index).

- [ ] **Step 6: Commit**

```bash
git add backend/src/nightcrate/db/migrations/0005.equipment_schema.sql backend/tests/test_mine_schema.py
git commit -m "feat: add is_mine column and partial index to owned equipment tables"
```

---

## Task 2: Pydantic models — add `is_mine` field to all 10 equipment types

**Files:**
- Modify: `backend/src/nightcrate/api/equipment_models.py`

Each of the 10 equipment types has three Pydantic models: `<Type>Create`, `<Type>Update`, `<Type>Response`. All three need `is_mine`. The file uses Pydantic v2 with `BaseModel` and `Field(...)` for descriptions.

- [ ] **Step 1: Add `is_mine` field to `CameraCreate`, `CameraUpdate`, `CameraResponse`**

In `backend/src/nightcrate/api/equipment_models.py`, find `class CameraCreate(BaseModel):` (around line 258). Add at the end of the class body, before the closing blank line of the class:

```python
    is_mine: bool = Field(False, description="Whether the user owns this camera")
```

Find `class CameraUpdate(BaseModel):` (around line 282). Add at the end of the class body:

```python
    is_mine: Optional[bool] = Field(None, description="Whether the user owns this camera")
```

Find `class CameraResponse(BaseModel):` (around line 306). Add alongside the other non-nested fields (model_name, cooled, etc.):

```python
    is_mine: bool
```

- [ ] **Step 2: Apply the same three-way addition to 9 other equipment types**

For each of the following types, find the three model classes and add the three lines shown in Step 1 (swapping `"camera"` in the descriptions with the natural name):

- `Telescope` (descriptions: "telescope")
- `Filter` (descriptions: "filter")
- `Mount` (descriptions: "mount")
- `Focuser` (descriptions: "focuser")
- `FilterWheel` (descriptions: "filter wheel")
- `Oag` (descriptions: "OAG")
- `GuideScope` (descriptions: "guide scope")
- `Computer` (descriptions: "computer")
- `Software` (descriptions: "software package")

Do **not** touch `Sensor`, `TelescopeConfiguration`, any lookup model, or any alias model.

- [ ] **Step 3: Run existing equipment API tests to confirm no regressions**

Run: `cd backend && uv run pytest tests/test_equipment_api.py -v`

Expected: all pre-existing tests pass (adding optional fields to Pydantic models is additive — no test should break).

- [ ] **Step 4: Commit**

```bash
git add backend/src/nightcrate/api/equipment_models.py
git commit -m "feat: add is_mine field to equipment Pydantic models (Create/Update/Response)"
```

---

## Task 3: API — list endpoint ordering and `?mine` filter

**Files:**
- Modify: `backend/src/nightcrate/api/equipment.py`
- Create: `backend/tests/test_equipment_mine_list.py`

Each of the 10 list endpoints (`list_cameras`, `list_telescopes`, etc.) needs:
1. A new `mine` query param (default `False`).
2. A WHERE clause that composes with the existing `include_retired` filter.
3. `ORDER BY is_mine DESC, <existing order>`.

- [ ] **Step 1: Write failing test — camera list default ordering puts mine first**

Create `backend/tests/test_equipment_mine_list.py`:

```python
"""List endpoints sort is_mine=1 first and support ?mine=true filter."""
import pytest
from httpx import ASGITransport, AsyncClient
from nightcrate.main import app


@pytest.mark.asyncio
async def test_camera_list_orders_mine_first(seeded_db):
    """Cameras with is_mine=1 appear before cameras with is_mine=0."""
    async with seeded_db as conn:
        # Mark the second camera as mine; the first stays unowned.
        await conn.execute(
            "UPDATE camera SET is_mine = 1 WHERE id = (SELECT id FROM camera ORDER BY id LIMIT 1 OFFSET 1)"
        )
        await conn.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/equipment/camera")
    assert response.status_code == 200
    cameras = response.json()
    assert len(cameras) >= 2
    # First row must be is_mine=1
    assert cameras[0]["is_mine"] is True
    # All remaining rows may be mixed but none before the first non-mine can be mine
    saw_non_mine = False
    for c in cameras:
        if not c["is_mine"]:
            saw_non_mine = True
        elif saw_non_mine:
            pytest.fail("is_mine=1 row appeared after is_mine=0 row")


@pytest.mark.asyncio
async def test_camera_list_mine_filter(seeded_db):
    """?mine=true returns only is_mine=1 rows."""
    async with seeded_db as conn:
        await conn.execute(
            "UPDATE camera SET is_mine = 1 WHERE id = (SELECT id FROM camera ORDER BY id LIMIT 1)"
        )
        await conn.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/equipment/camera?mine=true")
    assert response.status_code == 200
    cameras = response.json()
    assert len(cameras) == 1
    assert cameras[0]["is_mine"] is True


@pytest.mark.asyncio
async def test_camera_list_mine_false_returns_all(seeded_db):
    """?mine=false (or omitted) returns all rows including is_mine=0 and is_mine=1."""
    async with seeded_db as conn:
        await conn.execute(
            "UPDATE camera SET is_mine = 1 WHERE id = (SELECT id FROM camera ORDER BY id LIMIT 1)"
        )
        await conn.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/equipment/camera?mine=false")
    assert response.status_code == 200
    cameras = response.json()
    assert len(cameras) >= 2


@pytest.mark.asyncio
async def test_camera_list_mine_filter_composes_with_include_retired(seeded_db):
    """?mine=true&include_retired=true returns mine rows including retired ones."""
    async with seeded_db as conn:
        # Mark two cameras as mine, retire one
        rows = await conn.execute("SELECT id FROM camera ORDER BY id LIMIT 2")
        ids = [r[0] for r in await rows.fetchall()]
        assert len(ids) == 2
        await conn.execute("UPDATE camera SET is_mine = 1 WHERE id IN (?, ?)", ids)
        await conn.execute("UPDATE camera SET active = 0 WHERE id = ?", (ids[0],))
        await conn.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        active_only = await client.get("/api/equipment/camera?mine=true")
        with_retired = await client.get("/api/equipment/camera?mine=true&include_retired=true")
    assert active_only.status_code == 200
    assert with_retired.status_code == 200
    assert len(active_only.json()) == 1
    assert len(with_retired.json()) == 2
```

Note: the fixture name `seeded_db` is hypothetical — use whatever fixture the rest of `test_equipment_api.py` uses for a DB with seed data loaded. If no such fixture exists, add one in `backend/tests/conftest.py` that creates a temp DB, runs migrations, loads a minimal set of cameras via the seed loader or direct INSERTs.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd backend && uv run pytest tests/test_equipment_mine_list.py -v`

Expected: all fail. Reasons will include either `ordering` assertions or `?mine=true` param being ignored (the response contains unfiltered rows).

- [ ] **Step 3: Update `list_cameras` to support `?mine` and mine-first ordering**

In `backend/src/nightcrate/api/equipment.py`, locate `async def list_cameras(...)` (around line 1103). Replace the function body with:

```python
@router.get("/camera", response_model=list[CameraResponse])
async def list_cameras(
    include_retired: bool = Query(False, description="Include retired items"),
    mine: bool = Query(False, description="Return only items marked as mine"),
):
    async with get_db() as conn:
        conditions = []
        if not include_retired:
            conditions.append("active = 1")
        if mine:
            conditions.append("is_mine = 1")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await conn.execute(
            f"SELECT * FROM camera {where} ORDER BY is_mine DESC, model_name"
        )
        results = []
        for r in await rows.fetchall():
            results.append(await _build_camera_response(conn, _row_to_dict(r)))
        return results
```

- [ ] **Step 4: Run the camera tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_equipment_mine_list.py -v`

Expected: all 4 tests pass.

- [ ] **Step 5: Apply the same change to the 9 other list endpoints**

For each of these functions in `equipment.py`, replace the body using the same pattern — add `mine: bool = Query(False)`, build the `conditions` list, prepend `is_mine DESC` to the existing `ORDER BY`:

| Function | Existing ORDER BY column | Approx line |
|---|---|---|
| `list_telescopes` | `model_name` | 1277 |
| `list_filters` | (whatever it currently is — often `name`) | 1571 |
| `list_mounts` | `model_name` | 1883 |
| `list_focusers` | `model_name` | 2030 |
| `list_filter_wheels` | `model_name` | 2195 |
| `list_oags` | `model_name` | 2338 |
| `list_guide_scopes` | `model_name` | 2454 |
| `list_computers` | `model_name` | 2568 |
| `list_software` | `name` | 2673 |

For each, check the current `ORDER BY` column in the code (line numbers are approximate) and prepend `is_mine DESC,` to it. Keep existing behavior otherwise.

- [ ] **Step 6: Add two regression tests for other types**

Append to `backend/tests/test_equipment_mine_list.py`:

```python
@pytest.mark.asyncio
async def test_telescope_list_orders_mine_first(seeded_db):
    async with seeded_db as conn:
        rows = await conn.execute("SELECT id FROM telescope ORDER BY id LIMIT 2")
        ids = [r[0] for r in await rows.fetchall()]
        assert len(ids) == 2
        await conn.execute("UPDATE telescope SET is_mine = 1 WHERE id = ?", (ids[1],))
        await conn.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/equipment/telescope")
    assert response.status_code == 200
    telescopes = response.json()
    assert telescopes[0]["is_mine"] is True


@pytest.mark.asyncio
async def test_filter_list_mine_filter(seeded_db):
    async with seeded_db as conn:
        rows = await conn.execute("SELECT id FROM filter ORDER BY id LIMIT 1")
        fid = (await rows.fetchone())[0]
        await conn.execute("UPDATE filter SET is_mine = 1 WHERE id = ?", (fid,))
        await conn.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/equipment/filter?mine=true")
    assert response.status_code == 200
    assert all(f["is_mine"] for f in response.json())
    assert len(response.json()) == 1
```

- [ ] **Step 7: Run the full list test suite and verify pass**

Run: `cd backend && uv run pytest tests/test_equipment_mine_list.py -v`

Expected: all 6 tests pass.

- [ ] **Step 8: Run the full equipment API test to ensure no regressions**

Run: `cd backend && uv run pytest tests/test_equipment_api.py tests/test_rig_api.py -v`

Expected: all existing tests pass (adding optional query params and leading-column ordering is backwards-compatible).

- [ ] **Step 9: Commit**

```bash
git add backend/src/nightcrate/api/equipment.py backend/tests/test_equipment_mine_list.py
git commit -m "feat: equipment list endpoints support ?mine filter and order mine-first"
```

---

## Task 4: API — dedicated toggle endpoint `POST /<type>/{id}/mine`

**Files:**
- Modify: `backend/src/nightcrate/api/equipment.py`
- Modify: `backend/src/nightcrate/api/equipment_models.py`
- Create: `backend/tests/test_equipment_mine_toggle.py`

- [ ] **Step 1: Add a small `MineToggle` Pydantic model**

In `backend/src/nightcrate/api/equipment_models.py`, near the top of the file (alongside other shared types), add:

```python
class MineToggle(BaseModel):
    is_mine: bool = Field(..., description="True to mark as mine; False to unmark")
```

- [ ] **Step 2: Write failing test for camera toggle**

Create `backend/tests/test_equipment_mine_toggle.py`:

```python
"""POST /equipment/<type>/{id}/mine toggles the is_mine flag."""
import pytest
from httpx import ASGITransport, AsyncClient
from nightcrate.main import app


async def _get_first_id(seeded_db, table: str) -> int:
    async with seeded_db as conn:
        row = await (await conn.execute(f"SELECT id FROM {table} ORDER BY id LIMIT 1")).fetchone()
        assert row is not None, f"no rows in {table}"
        return row[0]


@pytest.mark.asyncio
async def test_camera_toggle_mine_on(seeded_db):
    camera_id = await _get_first_id(seeded_db, "camera")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/equipment/camera/{camera_id}/mine",
            json={"is_mine": True},
        )
    assert response.status_code == 200
    assert response.json()["is_mine"] is True

    # Round-trip: GET reflects the toggle
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        get_resp = await client.get(f"/api/equipment/camera/{camera_id}")
    assert get_resp.json()["is_mine"] is True


@pytest.mark.asyncio
async def test_camera_toggle_mine_off(seeded_db):
    camera_id = await _get_first_id(seeded_db, "camera")
    async with seeded_db as conn:
        await conn.execute("UPDATE camera SET is_mine = 1 WHERE id = ?", (camera_id,))
        await conn.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/equipment/camera/{camera_id}/mine",
            json={"is_mine": False},
        )
    assert response.status_code == 200
    assert response.json()["is_mine"] is False


@pytest.mark.asyncio
async def test_camera_toggle_mine_idempotent(seeded_db):
    """Toggling to the same state twice is a no-op."""
    camera_id = await _get_first_id(seeded_db, "camera")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post(f"/api/equipment/camera/{camera_id}/mine", json={"is_mine": True})
        r2 = await client.post(f"/api/equipment/camera/{camera_id}/mine", json={"is_mine": True})
    assert r1.status_code == 200 and r1.json()["is_mine"] is True
    assert r2.status_code == 200 and r2.json()["is_mine"] is True


@pytest.mark.asyncio
async def test_camera_toggle_mine_unknown_id(seeded_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/equipment/camera/99999999/mine",
            json={"is_mine": True},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("table,route", [
    ("telescope", "telescope"),
    ("filter", "filter"),
    ("mount", "mount"),
    ("focuser", "focuser"),
    ("filter_wheel", "filter-wheel"),
    ("oag", "oag"),
    ("guide_scope", "guide-scope"),
    ("computer", "computer"),
    ("software", "software"),
])
async def test_toggle_mine_other_types(seeded_db, table, route):
    item_id = await _get_first_id(seeded_db, table)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/equipment/{route}/{item_id}/mine",
            json={"is_mine": True},
        )
    assert response.status_code == 200, f"{table}: {response.status_code} {response.text}"
    assert response.json()["is_mine"] is True
```

- [ ] **Step 3: Run the tests and verify they fail**

Run: `cd backend && uv run pytest tests/test_equipment_mine_toggle.py -v`

Expected: all fail with 404 (no toggle route registered).

- [ ] **Step 4: Add toggle endpoint for camera**

In `backend/src/nightcrate/api/equipment.py`, add `MineToggle` to the existing `from .equipment_models import ...` imports.

After the `delete_camera` function (around line 1220), add:

```python
@router.post("/camera/{camera_id}/mine", response_model=CameraResponse)
async def toggle_camera_mine(camera_id: int, body: MineToggle):
    async with get_db() as conn:
        await _get_or_404(conn, "camera", camera_id, "Camera")
        await conn.execute(
            "UPDATE camera SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), camera_id),
        )
        await conn.commit()
        row = await _get_or_404(conn, "camera", camera_id, "Camera")
        return await _build_camera_response(conn, row)
```

- [ ] **Step 5: Run camera tests and verify they pass**

Run: `cd backend && uv run pytest tests/test_equipment_mine_toggle.py::test_camera_toggle_mine_on tests/test_equipment_mine_toggle.py::test_camera_toggle_mine_off tests/test_equipment_mine_toggle.py::test_camera_toggle_mine_idempotent tests/test_equipment_mine_toggle.py::test_camera_toggle_mine_unknown_id -v`

Expected: 4 pass.

- [ ] **Step 6: Add toggle endpoints for the 9 other types**

After each type's `delete_*` function, insert the equivalent toggle endpoint. Route patterns and response models per type:

| Type | Route | Param name | Response model | Table |
|---|---|---|---|---|
| telescope | `/telescope/{telescope_id}/mine` | `telescope_id` | `TelescopeResponse` | `telescope` |
| filter | `/filter/{filter_id}/mine` | `filter_id` | `FilterResponse` | `filter` |
| mount | `/mount/{mount_id}/mine` | `mount_id` | `MountResponse` | `mount` |
| focuser | `/focuser/{focuser_id}/mine` | `focuser_id` | `FocuserResponse` | `focuser` |
| filter_wheel | `/filter-wheel/{filter_wheel_id}/mine` | `filter_wheel_id` | `FilterWheelResponse` | `filter_wheel` |
| oag | `/oag/{oag_id}/mine` | `oag_id` | `OagResponse` | `oag` |
| guide_scope | `/guide-scope/{guide_scope_id}/mine` | `guide_scope_id` | `GuideScopeResponse` | `guide_scope` |
| computer | `/computer/{computer_id}/mine` | `computer_id` | `ComputerResponse` | `computer` |
| software | `/software/{software_id}/mine` | `software_id` | `SoftwareResponse` | `software` |

Each follows the same body pattern as the camera toggle. Example for telescope:

```python
@router.post("/telescope/{telescope_id}/mine", response_model=TelescopeResponse)
async def toggle_telescope_mine(telescope_id: int, body: MineToggle):
    async with get_db() as conn:
        await _get_or_404(conn, "telescope", telescope_id, "Telescope")
        await conn.execute(
            "UPDATE telescope SET is_mine = ? WHERE id = ?",
            (int(body.is_mine), telescope_id),
        )
        await conn.commit()
        row = await _get_or_404(conn, "telescope", telescope_id, "Telescope")
        return await _build_telescope_response(conn, row)
```

Use each type's existing `_build_*_response` helper (they already exist per type — see the rest of `equipment.py`).

- [ ] **Step 7: Run the parameterized test across all 10 types**

Run: `cd backend && uv run pytest tests/test_equipment_mine_toggle.py -v`

Expected: all 13 tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/nightcrate/api/equipment.py backend/src/nightcrate/api/equipment_models.py backend/tests/test_equipment_mine_toggle.py
git commit -m "feat: add POST /<type>/{id}/mine toggle endpoint for all 10 owned types"
```

---

## Task 5: API — `GET /equipment/mine-counts` endpoint

**Files:**
- Modify: `backend/src/nightcrate/api/equipment.py`
- Modify: `backend/src/nightcrate/api/equipment_models.py`
- Create: `backend/tests/test_equipment_mine_counts.py`

- [ ] **Step 1: Add the `MineCountsResponse` Pydantic model**

In `backend/src/nightcrate/api/equipment_models.py`, alongside `MineToggle`:

```python
class MineCountsResponse(BaseModel):
    cameras: int
    telescopes: int
    filters: int
    mounts: int
    focusers: int
    filter_wheels: int
    oags: int
    guide_scopes: int
    computers: int
    software: int
```

- [ ] **Step 2: Write failing test**

Create `backend/tests/test_equipment_mine_counts.py`:

```python
"""GET /equipment/mine-counts returns per-type counts of is_mine=1 rows."""
import pytest
from httpx import ASGITransport, AsyncClient
from nightcrate.main import app


@pytest.mark.asyncio
async def test_mine_counts_zero_when_nothing_owned(seeded_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/equipment/mine-counts")
    assert response.status_code == 200
    counts = response.json()
    for key in [
        "cameras", "telescopes", "filters", "mounts", "focusers",
        "filter_wheels", "oags", "guide_scopes", "computers", "software",
    ]:
        assert counts[key] == 0, f"{key} should be 0, got {counts[key]}"


@pytest.mark.asyncio
async def test_mine_counts_reflect_marked_items(seeded_db):
    async with seeded_db as conn:
        # Mark 2 cameras, 1 telescope, 3 filters as mine
        rows = await conn.execute("SELECT id FROM camera ORDER BY id LIMIT 2")
        cam_ids = [r[0] for r in await rows.fetchall()]
        await conn.execute("UPDATE camera SET is_mine = 1 WHERE id IN (?, ?)", cam_ids)

        rows = await conn.execute("SELECT id FROM telescope ORDER BY id LIMIT 1")
        tel_id = (await rows.fetchone())[0]
        await conn.execute("UPDATE telescope SET is_mine = 1 WHERE id = ?", (tel_id,))

        rows = await conn.execute("SELECT id FROM filter ORDER BY id LIMIT 3")
        fil_ids = [r[0] for r in await rows.fetchall()]
        await conn.execute(
            f"UPDATE filter SET is_mine = 1 WHERE id IN ({','.join('?' * len(fil_ids))})",
            fil_ids,
        )
        await conn.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/equipment/mine-counts")
    assert response.status_code == 200
    counts = response.json()
    assert counts["cameras"] == 2
    assert counts["telescopes"] == 1
    assert counts["filters"] == 3
    # Untouched types remain 0
    assert counts["mounts"] == 0
    assert counts["focusers"] == 0
    assert counts["filter_wheels"] == 0
    assert counts["oags"] == 0
    assert counts["guide_scopes"] == 0
    assert counts["computers"] == 0
    assert counts["software"] == 0


@pytest.mark.asyncio
async def test_mine_counts_ignores_retired(seeded_db):
    """Retired (is_mine=1, active=0) items should still count as mine."""
    async with seeded_db as conn:
        rows = await conn.execute("SELECT id FROM camera ORDER BY id LIMIT 1")
        cam_id = (await rows.fetchone())[0]
        await conn.execute(
            "UPDATE camera SET is_mine = 1, active = 0 WHERE id = ?", (cam_id,)
        )
        await conn.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/equipment/mine-counts")
    assert response.status_code == 200
    # Retired items with is_mine=1 still show in the count — retirement is orthogonal to ownership.
    assert response.json()["cameras"] == 1
```

- [ ] **Step 3: Run tests and verify they fail**

Run: `cd backend && uv run pytest tests/test_equipment_mine_counts.py -v`

Expected: all fail with 404.

- [ ] **Step 4: Implement the endpoint**

In `backend/src/nightcrate/api/equipment.py`, add `MineCountsResponse` to the imports from `equipment_models`. Place the endpoint at the very top of the router (before the first existing route, so it doesn't accidentally match a `GET /camera/{id}` path):

```python
@router.get("/mine-counts", response_model=MineCountsResponse)
async def get_mine_counts():
    """Per-type counts of equipment marked as mine. Retired items still count."""
    mapping = {
        "cameras": "camera",
        "telescopes": "telescope",
        "filters": "filter",
        "mounts": "mount",
        "focusers": "focuser",
        "filter_wheels": "filter_wheel",
        "oags": "oag",
        "guide_scopes": "guide_scope",
        "computers": "computer",
        "software": "software",
    }
    counts: dict[str, int] = {}
    async with get_db() as conn:
        for response_key, table in mapping.items():
            row = await (
                await conn.execute(f"SELECT COUNT(*) FROM {table} WHERE is_mine = 1")
            ).fetchone()
            counts[response_key] = row[0] if row else 0
    return counts
```

Place this function between the router definition and the first existing endpoint, so FastAPI route matching prioritizes `/mine-counts` over `/{camera_id}` variants. In practice, since there's no `GET /equipment/{something}` catch-all route (all gets are scoped under `/equipment/<table>/...`), placement doesn't affect correctness — but keeping it at the top makes the file easier to scan.

- [ ] **Step 5: Run tests and verify they pass**

Run: `cd backend && uv run pytest tests/test_equipment_mine_counts.py -v`

Expected: all 3 pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/nightcrate/api/equipment.py backend/src/nightcrate/api/equipment_models.py backend/tests/test_equipment_mine_counts.py
git commit -m "feat: add GET /equipment/mine-counts endpoint"
```

---

## Task 6: Seed loader regression — mine flag survives re-seed

**Files:**
- Create: `backend/tests/test_seed_loader_mine.py`

The seed loader compares CSV-hash against stored seed_hash to decide whether to re-seed. Because `is_mine` is not a CSV column, it's not in the hash contract — marking an item as mine should not trigger a re-seed of that row, and a re-seed must not stomp the flag.

- [ ] **Step 1: Write the regression test**

Create `backend/tests/test_seed_loader_mine.py`:

```python
"""Seed-loader regression: is_mine must survive re-seed and not trigger stomping."""
import pytest
from nightcrate.seed_loader.loader import load_seeds


@pytest.mark.asyncio
async def test_is_mine_preserved_across_reseed(seeded_db, csv_root):
    """
    Flow:
      1. seed_loader runs at test-db init (first_run)
      2. Mark a seed-loaded camera as is_mine=1
      3. Run seed_loader again (update mode)
      4. Assert: camera still has is_mine=1
      5. Assert: the row's hash column is unchanged (not re-written)
    """
    async with seeded_db as conn:
        row = await (await conn.execute(
            "SELECT id, seed_key, seed_hash FROM camera "
            "WHERE source = 'seed' AND seed_key IS NOT NULL "
            "ORDER BY id LIMIT 1"
        )).fetchone()
        assert row is not None, "no seed-loaded cameras found for test"
        cam_id, seed_key, original_hash = row

        # Mark as mine
        await conn.execute("UPDATE camera SET is_mine = 1 WHERE id = ?", (cam_id,))
        await conn.commit()

    # Re-run seed loader in update mode (csv_root fixture points at seed/ dir)
    report = load_seeds(csv_root=csv_root, db_path=seeded_db.db_path, mode="update")
    assert report.success, f"seed load failed: {report.errors}"

    async with seeded_db as conn:
        row = await (await conn.execute(
            "SELECT is_mine, seed_hash FROM camera WHERE id = ?", (cam_id,)
        )).fetchone()
        assert row is not None
        is_mine_after, hash_after = row
        assert is_mine_after == 1, "is_mine was stomped by re-seed"
        assert hash_after == original_hash, "seed_hash changed — re-seed rewrote the row"
```

Note: the fixture names `seeded_db`, `csv_root`, and `seeded_db.db_path` assume the project's existing seed-loader tests expose these. Look at `backend/tests/test_seed_loader.py` for the actual fixture names and function signatures, and adapt. `load_seeds` may have a different entry-point name in `seed_loader/loader.py` — verify before writing.

- [ ] **Step 2: Run the test and verify it passes**

Run: `cd backend && uv run pytest tests/test_seed_loader_mine.py -v`

Expected: passes. If it fails because the seed loader's hash contract does include all DB columns (not just CSV columns), that's a genuine bug — stop and discuss with Fred; do not work around it.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_seed_loader_mine.py
git commit -m "test: regression for is_mine survival across re-seed"
```

---

## Task 7: Frontend API client — types and fetch functions

**Files:**
- Modify: `frontend/src/api/equipment.ts`

- [ ] **Step 1: Add `is_mine` to all 10 equipment type interfaces**

In `frontend/src/api/equipment.ts`, find each interface below and add `is_mine: boolean;` as a new field (place near top of the interface, alongside primary fields like `id` and `model_name`):

- `Camera`
- `Telescope`
- `Filter`
- `Mount`
- `Focuser`
- `FilterWheel`
- `Oag`
- `GuideScope`
- `Computer`
- `Software`

If the file uses separate `*Create` / `*Update` input interfaces, add `is_mine?: boolean;` to those as well. If inputs are inline object types within fetch functions, no change is needed there.

- [ ] **Step 2: Add `mine` query param to all 10 fetch list functions**

Each list function currently accepts `(includeRetired?: boolean)`. Update the signature to `(includeRetired = false, mine = false)` and append `&mine=true` to the URL when `mine` is true. Example pattern for `fetchCameras`:

```typescript
export async function fetchCameras(
  includeRetired = false,
  mine = false,
): Promise<Camera[]> {
  const params = new URLSearchParams();
  if (includeRetired) params.set("include_retired", "true");
  if (mine) params.set("mine", "true");
  const qs = params.toString();
  const url = `/api/equipment/camera${qs ? `?${qs}` : ""}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch cameras: ${res.status}`);
  return res.json();
}
```

Apply the same shape to `fetchTelescopes`, `fetchFilters`, `fetchMounts`, `fetchFocusers`, `fetchFilterWheels`, `fetchOags`, `fetchGuideScopes`, `fetchComputers`, `fetchSoftware`.

- [ ] **Step 3: Add `toggleEquipmentMine` dispatcher function**

At the bottom of `equipment.ts`, add a dispatcher that routes to the correct endpoint based on the table name:

```typescript
const MINE_ROUTE_BY_TABLE: Record<string, string> = {
  camera: "camera",
  telescope: "telescope",
  filter: "filter",
  mount: "mount",
  focuser: "focuser",
  filter_wheel: "filter-wheel",
  oag: "oag",
  guide_scope: "guide-scope",
  computer: "computer",
  software: "software",
};

export async function toggleEquipmentMine(
  table: string,
  id: number,
  isMine: boolean,
): Promise<unknown> {
  const route = MINE_ROUTE_BY_TABLE[table];
  if (!route) throw new Error(`Unknown equipment table: ${table}`);
  const res = await fetch(`/api/equipment/${route}/${id}/mine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_mine: isMine }),
  });
  if (!res.ok) throw new Error(`Failed to toggle mine: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 4: Add `fetchMineCounts`**

Also at the bottom of `equipment.ts`:

```typescript
export interface MineCounts {
  cameras: number;
  telescopes: number;
  filters: number;
  mounts: number;
  focusers: number;
  filter_wheels: number;
  oags: number;
  guide_scopes: number;
  computers: number;
  software: number;
}

export async function fetchMineCounts(): Promise<MineCounts> {
  const res = await fetch("/api/equipment/mine-counts");
  if (!res.ok) throw new Error(`Failed to fetch mine counts: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 5: Verify build passes**

Run: `cd frontend && npm run build`

Expected: TypeScript compiles, vite build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/equipment.ts
git commit -m "feat(frontend): add is_mine types and toggle/counts API clients"
```

---

## Task 8: Frontend — clickable star column in `EquipmentList`

**Files:**
- Modify: `frontend/src/components/equipment/EquipmentList.tsx`

The star column is inserted as the leftmost column. Click flips the boolean optimistically and POSTs the toggle. On error, rolls back with a Snackbar.

- [ ] **Step 1: Add required imports to `EquipmentList.tsx`**

At the top of `frontend/src/components/equipment/EquipmentList.tsx`, add to the existing MUI imports:

```typescript
import Snackbar from "@mui/material/Snackbar";
import Alert from "@mui/material/Alert";
import Tooltip from "@mui/material/Tooltip";
import StarIcon from "@mui/icons-material/Star";
import StarOutlineIcon from "@mui/icons-material/StarOutline";
```

From `@/api/equipment`, also import:

```typescript
import { toggleEquipmentMine } from "@/api/equipment";
```

- [ ] **Step 2: Add `mineOnly` prop to `EquipmentListProps` and pass it to the fetch**

Update the interface:

```typescript
interface EquipmentListProps<T extends { id: number }> {
  title: string;
  addLabel?: string;
  queryKey: string;
  tableName: string;
  fetchFn: (includeRetired?: boolean, mine?: boolean) => Promise<T[]>;
  deleteFn: (id: number) => Promise<unknown>;
  columns: GridColDef<T>[];
  getItemName: (item: T) => string;
  FormDialog: React.ComponentType<{
    open: boolean;
    item: T | null;
    onClose: () => void;
    onSaved: () => void;
  }>;
  renderDetail?: (item: T) => React.ReactNode;
  /** When true, filter the list to items with is_mine=true. */
  mineOnly?: boolean;
}
```

In the function-body destructuring, add `mineOnly = false`. Update the query:

```typescript
  const { data: items = [], isLoading } = useQuery({
    queryKey: [queryKey, { showRetired, mineOnly }],
    queryFn: () => fetchFn(showRetired, mineOnly),
  });
```

- [ ] **Step 3: Extend the row type and add the star column**

The generic `T` needs to include `is_mine`. Extend the constraint:

```typescript
export default function EquipmentList<T extends { id: number; active?: boolean; is_mine?: boolean }>({
```

Add snackbar state at the top of the function body:

```typescript
  const [mineError, setMineError] = useState<string | null>(null);
```

Add a helper that toggles optimistically. Place it after `handleRestore`:

```typescript
  const handleMineToggle = async (item: T) => {
    const newValue = !item.is_mine;
    // Optimistic cache update — flip is_mine on the row.
    queryClient.setQueryData<T[]>(
      [queryKey, { showRetired, mineOnly }],
      (prev) =>
        prev?.map((row) =>
          row.id === item.id ? ({ ...row, is_mine: newValue } as T) : row,
        ) ?? prev,
    );
    try {
      await toggleEquipmentMine(tableName, item.id, newValue);
      // Invalidate the list and mine-counts so sidebar updates too.
      void queryClient.invalidateQueries({ queryKey: [queryKey] });
      void queryClient.invalidateQueries({ queryKey: ["mine-counts"] });
    } catch (err) {
      // Roll back
      queryClient.setQueryData<T[]>(
        [queryKey, { showRetired, mineOnly }],
        (prev) =>
          prev?.map((row) =>
            row.id === item.id ? ({ ...row, is_mine: !newValue } as T) : row,
          ) ?? prev,
      );
      setMineError(
        err instanceof Error ? err.message : "Failed to update 'mine' status",
      );
    }
  };
```

Define the star column (put this before the `actionsColumn` definition):

```typescript
  const mineColumn: GridColDef<T> = {
    field: "is_mine",
    headerName: "",
    width: 48,
    sortable: false,
    filterable: false,
    renderHeader: () => (
      <Tooltip title="Mine">
        <StarOutlineIcon fontSize="small" />
      </Tooltip>
    ),
    renderCell: (params) => {
      const isMine = Boolean(params.row.is_mine);
      return (
        <IconButton
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            void handleMineToggle(params.row);
          }}
          aria-label={
            isMine
              ? `Remove ${getItemName(params.row)} from My Equipment`
              : `Add ${getItemName(params.row)} to My Equipment`
          }
        >
          {isMine ? (
            <StarIcon fontSize="small" color="primary" />
          ) : (
            <StarOutlineIcon fontSize="small" />
          )}
        </IconButton>
      );
    },
  };
```

Update `allColumns` to include the star column at the front:

```typescript
  const allColumns = [mineColumn, ...columns, actionsColumn];
```

- [ ] **Step 4: Add the Snackbar inside the return**

Before the closing `</Box>` of the component's return JSX, add:

```tsx
      <Snackbar
        open={mineError !== null}
        autoHideDuration={4000}
        onClose={() => setMineError(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="error" onClose={() => setMineError(null)}>
          {mineError}
        </Alert>
      </Snackbar>
```

- [ ] **Step 5: Update the empty-state behavior (optional but spec'd)**

When `mineOnly` is true and `items.length === 0` and `!isLoading`, render the DataGrid's default `noRowsOverlay` with a custom message. MUI DataGrid supports `slots.noRowsOverlay`. Add to the `DataGrid` prop list:

```tsx
          slots={{
            noRowsOverlay: mineOnly
              ? () => (
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      height: "100%",
                      p: 2,
                      color: "text.secondary",
                      fontStyle: "italic",
                      textAlign: "center",
                    }}
                  >
                    No equipment marked as yours yet. Open any item and check "Mark as
                    mine", or click the star in a list.
                  </Box>
                )
              : undefined,
          }}
```

(Leave the default overlay when `mineOnly` is false.)

- [ ] **Step 6: Build and verify no TS errors**

Run: `cd frontend && npm run build`

Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/equipment/EquipmentList.tsx
git commit -m "feat(frontend): add clickable star column and mineOnly filter to EquipmentList"
```

---

## Task 9: Frontend — `MineCheckbox` shared component and wire into all 10 form dialogs

**Files:**
- Create: `frontend/src/components/equipment/shared/MineCheckbox.tsx`
- Modify: each of 10 form dialogs

- [ ] **Step 1: Create the shared `MineCheckbox` component**

Create `frontend/src/components/equipment/shared/MineCheckbox.tsx`:

```tsx
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import StarIcon from "@mui/icons-material/Star";
import StarOutlineIcon from "@mui/icons-material/StarOutline";

interface MineCheckboxProps {
  value: boolean;
  onChange: (value: boolean) => void;
}

export default function MineCheckbox({ value, onChange }: MineCheckboxProps) {
  return (
    <FormControlLabel
      control={
        <Checkbox
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
          icon={<StarOutlineIcon />}
          checkedIcon={<StarIcon color="primary" />}
        />
      }
      label={<Box sx={{ fontSize: "0.875rem" }}>Mark as mine (I own this)</Box>}
      sx={{ mb: 1 }}
    />
  );
}
```

- [ ] **Step 2: Wire into `CameraFormDialog`**

In `frontend/src/components/equipment/CameraFormDialog.tsx`, import:

```typescript
import MineCheckbox from "@/components/equipment/shared/MineCheckbox";
```

In the form's local state (where fields like `model_name`, `manufacturer_id` are initialized from the `camera` prop), add:

```typescript
const [isMine, setIsMine] = useState<boolean>(camera?.is_mine ?? false);
```

Inside the `useEffect` that resets state when `camera` changes, add:

```typescript
setIsMine(camera?.is_mine ?? false);
```

In the save/submit handler, include `is_mine: isMine` in the payload passed to create/update.

In the JSX, place `<MineCheckbox value={isMine} onChange={setIsMine} />` near the top of the form (after the manufacturer/model fields, before the longer fields).

- [ ] **Step 3: Run the frontend build**

Run: `cd frontend && npm run build`

Expected: build succeeds.

- [ ] **Step 4: Wire into the 9 other form dialogs**

Repeat Step 2 for each of these form dialog files. In each, the existing prop name matches the type (e.g., `telescope`, `filter`, `mount`, etc. — check the prop interface at the top of each file):

- `TelescopeFormDialog.tsx` (prop: `telescope`)
- `FilterFormDialog.tsx` (prop: `filter`)
- `MountFormDialog.tsx` (prop: `mount`)
- `FocuserFormDialog.tsx` (prop: `focuser`)
- `FilterWheelFormDialog.tsx` (prop: `filterWheel`)
- `OagFormDialog.tsx` (prop: `oag`)
- `GuideScopeFormDialog.tsx` (prop: `guideScope`)
- `ComputerFormDialog.tsx` (prop: `computer`)
- `SoftwareFormDialog.tsx` (prop: `software`)

Apply these edits per file:
  1. Import `MineCheckbox`.
  2. Add `isMine` state initialized from `<prop>?.is_mine ?? false`.
  3. Reset `isMine` in the prop-change `useEffect`.
  4. Include `is_mine: isMine` in the create/update payload.
  5. Render `<MineCheckbox value={isMine} onChange={setIsMine} />` near the top of the form.

- [ ] **Step 5: Build and verify**

Run: `cd frontend && npm run build`

Expected: build succeeds with no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/equipment/shared/MineCheckbox.tsx frontend/src/components/equipment/CameraFormDialog.tsx frontend/src/components/equipment/TelescopeFormDialog.tsx frontend/src/components/equipment/FilterFormDialog.tsx frontend/src/components/equipment/MountFormDialog.tsx frontend/src/components/equipment/FocuserFormDialog.tsx frontend/src/components/equipment/FilterWheelFormDialog.tsx frontend/src/components/equipment/OagFormDialog.tsx frontend/src/components/equipment/GuideScopeFormDialog.tsx frontend/src/components/equipment/ComputerFormDialog.tsx frontend/src/components/equipment/SoftwareFormDialog.tsx
git commit -m "feat(frontend): add 'Mark as mine' checkbox to all 10 equipment form dialogs"
```

---

## Task 10: Frontend — `EquipmentPage` routing for `my-*` slugs

**Files:**
- Modify: `frontend/src/pages/EquipmentPage.tsx`
- Modify: each of the 10 per-type list wrapper components (`CameraList.tsx`, etc.)

The 10 list wrappers currently don't accept a `mineOnly` prop — they just render `<EquipmentList ... />`. Add a `mineOnly` prop to each wrapper and forward it to `EquipmentList`.

- [ ] **Step 1: Accept `mineOnly` on `CameraList`**

In `frontend/src/components/equipment/CameraList.tsx`, change the default export signature:

```typescript
export default function CameraList({ mineOnly = false }: { mineOnly?: boolean } = {}) {
  return (
    <EquipmentList<Camera>
      title={mineOnly ? "My Cameras" : "Cameras"}
      queryKey={mineOnly ? "my-cameras" : "cameras"}
      tableName="camera"
      fetchFn={fetchCameras}
      deleteFn={deleteCamera}
      columns={columns}
      getItemName={(c) => c.model_name}
      FormDialog={CameraForm}
      mineOnly={mineOnly}
      renderDetail={(item) => (
        // ... existing detail
      )}
    />
  );
}
```

(The `title` and `queryKey` vary based on `mineOnly` so the TanStack Query cache doesn't collide and the header updates.)

- [ ] **Step 2: Apply the same change to the 9 other list wrappers**

Repeat for: `TelescopeList.tsx`, `FilterList.tsx`, `MountList.tsx`, `FocuserList.tsx`, `FilterWheelList.tsx`, `OagList.tsx`, `GuideScopeList.tsx`, `ComputerList.tsx`, `SoftwareList.tsx`.

Each wrapper accepts `{ mineOnly = false }`. Titles for the `mineOnly` case:

- Telescope → "My OTAs" (vs. existing "OTAs")
- Filter → "My Filters"
- Mount → "My Mounts"
- Focuser → "My Focusers"
- FilterWheel → "My Filter Wheels"
- Oag → "My OAGs"
- GuideScope → "My Guide Scopes"
- Computer → "My Computers"
- Software → "My Software"

And queryKeys: `my-telescopes`, `my-filters`, `my-mounts`, `my-focusers`, `my-filter-wheels`, `my-oags`, `my-guide-scopes`, `my-computers`, `my-software`.

- [ ] **Step 3: Route `my-*` slugs in `EquipmentPage`**

In `frontend/src/pages/EquipmentPage.tsx`, replace the `switch (category)` block with:

```typescript
  const content = (() => {
    switch (category) {
      case "cameras":
        return <CameraList />;
      case "my-cameras":
        return <CameraList mineOnly />;
      case "telescopes":
        return <TelescopeList />;
      case "my-telescopes":
        return <TelescopeList mineOnly />;
      case "filters":
        return <FilterList />;
      case "my-filters":
        return <FilterList mineOnly />;
      case "sensors":
        return <SensorList />;
      case "mounts":
        return <MountList />;
      case "my-mounts":
        return <MountList mineOnly />;
      case "focusers":
        return <FocuserList />;
      case "my-focusers":
        return <FocuserList mineOnly />;
      case "filter-wheels":
        return <FilterWheelList />;
      case "my-filter-wheels":
        return <FilterWheelList mineOnly />;
      case "oags":
        return <OagList />;
      case "my-oags":
        return <OagList mineOnly />;
      case "guide-scopes":
        return <GuideScopeList />;
      case "my-guide-scopes":
        return <GuideScopeList mineOnly />;
      case "computers":
        return <ComputerList />;
      case "my-computers":
        return <ComputerList mineOnly />;
      case "software":
        return <SoftwareList />;
      case "my-software":
        return <SoftwareList mineOnly />;
      case "manufacturers":
        return <ManufacturerList />;
      case "lookup-tables":
        return <LookupTablesPanel />;
      default:
        return <EquipmentPlaceholder category={category} />;
    }
  })();
```

- [ ] **Step 4: Build and verify**

Run: `cd frontend && npm run build`

Expected: build passes.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/EquipmentPage.tsx frontend/src/components/equipment/CameraList.tsx frontend/src/components/equipment/TelescopeList.tsx frontend/src/components/equipment/FilterList.tsx frontend/src/components/equipment/MountList.tsx frontend/src/components/equipment/FocuserList.tsx frontend/src/components/equipment/FilterWheelList.tsx frontend/src/components/equipment/OagList.tsx frontend/src/components/equipment/GuideScopeList.tsx frontend/src/components/equipment/ComputerList.tsx frontend/src/components/equipment/SoftwareList.tsx
git commit -m "feat(frontend): route my-* slugs to per-type lists with mineOnly filter"
```

---

## Task 11: Frontend — sidebar "MY EQUIPMENT" group with reactive sub-items

**Files:**
- Modify: `frontend/src/components/equipment/EquipmentSidebar.tsx`

The sidebar fetches `mine-counts` on mount, renders a new top group "MY EQUIPMENT", and shows sub-items only for types where the count > 0. When zero items are owned, shows a muted italic help line.

- [ ] **Step 1: Add imports and data fetch**

In `frontend/src/components/equipment/EquipmentSidebar.tsx`, add imports at the top:

```typescript
import { useQuery } from "@tanstack/react-query";
import { fetchMineCounts, type MineCounts } from "@/api/equipment";
```

Inside the `EquipmentSidebar` function, before the `defaultExpanded` line, add:

```typescript
  const { data: mineCounts } = useQuery<MineCounts>({
    queryKey: ["mine-counts"],
    queryFn: fetchMineCounts,
  });
```

- [ ] **Step 2: Define the "My Equipment" group content**

Add a helper inside the function, above the `return`:

```typescript
  const MINE_ITEMS: Array<{ id: string; label: string; countKey: keyof MineCounts }> = [
    { id: "my-cameras", label: "Cameras", countKey: "cameras" },
    { id: "my-telescopes", label: "OTAs", countKey: "telescopes" },
    { id: "my-filters", label: "Filters", countKey: "filters" },
    { id: "my-mounts", label: "Mounts", countKey: "mounts" },
    { id: "my-focusers", label: "Focusers", countKey: "focusers" },
    { id: "my-filter-wheels", label: "Filter Wheels", countKey: "filter_wheels" },
    { id: "my-oags", label: "OAGs", countKey: "oags" },
    { id: "my-guide-scopes", label: "Guide Scopes", countKey: "guide_scopes" },
    { id: "my-computers", label: "Computers", countKey: "computers" },
    { id: "my-software", label: "Software", countKey: "software" },
  ];

  const visibleMineItems = MINE_ITEMS.filter(
    (it) => (mineCounts?.[it.countKey] ?? 0) > 0,
  );
  const totalMine = mineCounts
    ? Object.values(mineCounts).reduce((s, n) => s + n, 0)
    : 0;
```

- [ ] **Step 3: Render the "MY EQUIPMENT" group before the existing groups**

Update the `defaultExpandedItems` to include `"group-my-equipment"`:

```typescript
  const defaultExpanded = ["group-my-equipment", ...GROUPS.map((g) => g.id)];
```

In the JSX, inside the `<SimpleTreeView>` and before the `{GROUPS.map(...)}` line, add:

```tsx
        <TreeItem
          itemId="group-my-equipment"
          label={
            <Typography
              variant="caption"
              fontWeight={700}
              sx={{
                textTransform: "uppercase",
                letterSpacing: 0.8,
                color: "text.secondary",
              }}
            >
              My Equipment
            </Typography>
          }
        >
          {totalMine === 0 ? (
            <TreeItem
              itemId="my-empty-hint"
              disabled
              label={
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ fontStyle: "italic", lineHeight: 1.4, display: "block", py: 0.5 }}
                >
                  Click the star on any equipment row to add it here.
                </Typography>
              }
            />
          ) : (
            visibleMineItems.map((item) => (
              <TreeItem key={item.id} itemId={item.id} label={item.label} />
            ))
          )}
        </TreeItem>
```

- [ ] **Step 4: Guard the `onSelectedItemsChange` handler against the hint item**

Update the existing handler in `SimpleTreeView` so the disabled hint can't be activated:

```typescript
        onSelectedItemsChange={(_event, itemId) => {
          if (itemId && !itemId.startsWith("group-") && itemId !== "my-empty-hint") {
            onSelectCategory(itemId);
          }
        }}
```

- [ ] **Step 5: Build and verify**

Run: `cd frontend && npm run build`

Expected: build passes.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/equipment/EquipmentSidebar.tsx
git commit -m "feat(frontend): add My Equipment sidebar group with reactive sub-items"
```

---

## Task 12: Frontend — rig-builder dropdowns surface "My Equipment" first

**Files:**
- Modify: `frontend/src/components/rigs/RigFormDialog.tsx`

Every `Autocomplete` in the rig form already uses `groupBy={(o) => o.manufacturer_name}` (or similar). The plan: introduce a small helper that (a) duplicates "is_mine" options into a virtual group and (b) renders a star indicator in `renderOption`. Apply to every dropdown.

- [ ] **Step 1: Add a shared helper at the top of `RigFormDialog.tsx`**

In `frontend/src/components/rigs/RigFormDialog.tsx`, at the top (after imports), add:

```typescript
const MINE_GROUP_LABEL = "My Equipment";

/**
 * Pre-process an option list so is_mine=true items appear both in a flat
 * "My Equipment" virtual group at the top AND in their manufacturer group.
 * Returns a new array with duplicates. Caller's `groupBy` must use
 * `__mine_group` when present.
 */
function withMineGroup<T extends { is_mine?: boolean }>(options: T[]): (T & { __mine_group?: string })[] {
  const result: (T & { __mine_group?: string })[] = [];
  // Virtual group entries first
  for (const opt of options) {
    if (opt.is_mine) {
      result.push({ ...opt, __mine_group: MINE_GROUP_LABEL });
    }
  }
  // Then the regular entries (unchanged)
  for (const opt of options) {
    result.push(opt);
  }
  return result;
}
```

Also add imports:

```typescript
import StarIcon from "@mui/icons-material/Star";
```

- [ ] **Step 2: Update the camera dropdown (and the other Autocompletes) to use the helper**

For each `<Autocomplete>` in `RigFormDialog.tsx` that represents an equipment picker (there are approximately 9 — camera, OTA, filter wheel, filter(s), mount, focuser, OAG, guide scope, guide camera, software), apply these three changes:

1. Wrap the `options` prop with `withMineGroup`:

```tsx
options={withMineGroup(cameraOptions)}
```

2. Change `groupBy` to prefer the virtual group label:

```tsx
groupBy={(o) => o.__mine_group ?? o.manufacturer_name}
```

3. Add a `renderOption` that shows a star when `is_mine`:

```tsx
renderOption={(props, option) => (
  <li {...props}>
    {option.is_mine && (
      <StarIcon fontSize="small" color="primary" sx={{ mr: 0.75 }} />
    )}
    {/* Whatever existing label the component was rendering — check the current code.
        For simple options this is usually just `option.model_name` or `option.name`.
        Preserve the pre-existing label structure. */}
    {option.model_name ?? option.name}
  </li>
)}
```

For the software Autocomplete (line ~603 in the file, uses `groupBy={(o) => o.category}`), use a slightly different variant: group by `__mine_group ?? o.category` instead of manufacturer. Software is multi-select, so verify the Autocomplete's `multiple` prop stays true and `isOptionEqualToValue` (if set) compares on id — if not, add `isOptionEqualToValue={(a, b) => a.id === b.id}` to handle the duplicated entries correctly.

4. For every Autocomplete, add `isOptionEqualToValue={(a, b) => a.id === b.id}` if not already present. This is essential because the option list contains duplicates (same id appears twice, once in the "My Equipment" virtual group and once in its manufacturer group).

5. Extend each local option type in `RigFormDialog.tsx` with `__mine_group?: string` and `is_mine?: boolean` so the `groupBy` / `renderOption` callbacks type-check. Search the file for `interface CameraOption`, `interface FilterWheelOption`, `interface FilterOption`, `interface SimpleOption`, `interface GuideScopeOption`, `interface SoftwareOption` (or their `type` equivalents) and add those two fields. If the option types come from `@/api/equipment`, update those source interfaces instead (the `is_mine: boolean` was already added in Task 7; `__mine_group` is a display-only concern and lives in `RigFormDialog.tsx` via intersection through `withMineGroup`).

- [ ] **Step 3: Build and verify**

Run: `cd frontend && npm run build`

Expected: build passes.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/rigs/RigFormDialog.tsx
git commit -m "feat(frontend): surface My Equipment at top of rig-builder dropdowns"
```

---

## Task 13: Final pre-commit checks and smoke test

**Files:** (no changes)

- [ ] **Step 1: Full backend checks**

Run from `backend/`:

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run bandit -r src/
uv run pytest
```

Expected: all four pass. If format check fails, run `uv run ruff format src/ tests/` and commit the formatting change.

- [ ] **Step 2: Frontend build**

Run: `cd frontend && npm run build`

Expected: build succeeds.

- [ ] **Step 3: Manual smoke test**

Start the app:

```bash
make dev
```

Walk through the smoke-test script from the spec (Section "Testing > Manual smoke test"):

1. Star a camera in the Cameras list → sidebar "My Equipment > Cameras" appears.
2. Click "My Equipment > Cameras" in the sidebar → only the starred camera shows, star filled.
3. Click the star again in this filtered view → row disappears optimistically; next refresh confirms it's gone.
4. Star 2 cameras and 2 OTAs. Open the Rig form (`/rigs` → Add Rig). Camera dropdown: observe a "My Equipment" section at the top with the 2 starred cameras; scroll down and observe the same 2 cameras also appear under their manufacturer groups, each with a star.
5. Open the filter edit dialog for a filter you own, toggle "Mark as mine" off, save. The filter unmarks from the list and disappears from "My Filters".
6. Unstar everything. The sidebar shows only the "MY EQUIPMENT" header and the help message "Click the star on any equipment row to add it here."
7. With the database recreated from scratch (see Task 1 Step 3), star a seed-loaded item, then re-run the seed loader (`uv run python -m nightcrate.seed_loader --db <path> --csv-root backend/src/nightcrate/data/seed/`). Confirm the star stays on and no re-seed error appears.

- [ ] **Step 4: Final integration commit (if anything changed)**

If any changes were needed to pass checks, commit them:

```bash
git status
git add <changed files>
git commit -m "chore: fix lint/format after My Equipment implementation"
```

If nothing changed, skip this step.

- [ ] **Step 5: Sync docs and bump version (handoff to finalize-session)**

Invoke the `sync-docs` skill to update `PLAN.md`, `CLAUDE.md`, and `DB_SCHEMA_DDL.sql` with the new feature, then `finalize-session` to bump the version, commit, push, and open the PR.

---

## Coverage map (spec → tasks)

| Spec section | Task(s) |
|---|---|
| Schema — is_mine column on 10 tables | Task 1 |
| Schema — partial indexes | Task 1 |
| Schema — seed-loader interaction | Task 6 |
| API — `is_mine` in response models | Task 2 |
| API — `is_mine` in create/update models | Task 2 |
| API — list default ordering `is_mine DESC` | Task 3 |
| API — `?mine=true` filter | Task 3 |
| API — toggle endpoint | Task 4 |
| API — mine-counts endpoint | Task 5 |
| Frontend — sidebar MY EQUIPMENT group | Task 11 |
| Frontend — reactive sub-items per type | Task 11 |
| Frontend — zero-state help line | Task 11 |
| Frontend — star column in EquipmentList | Task 8 |
| Frontend — optimistic toggle w/ rollback | Task 8 |
| Frontend — `mineOnly` prop + empty state | Tasks 8, 10 |
| Frontend — MineCheckbox in 10 form dialogs | Task 9 |
| Frontend — EquipmentPage routing for my-* | Task 10 |
| Frontend — Rig dropdowns My Equipment group + star | Task 12 |
| Testing — backend parametrized toggle tests | Task 4 |
| Testing — list ordering/filter tests (3 types) | Task 3 |
| Testing — mine-counts tests | Task 5 |
| Testing — seed-loader regression | Task 6 |
| Testing — frontend build gate | Tasks 7–12 |
| Testing — manual smoke | Task 13 |
