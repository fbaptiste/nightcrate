"""Round-trip tests for the v0.34.0 planner UI-state settings fields."""

import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.core.config import PlannerSortEntry, Settings, get_settings, update_settings
from nightcrate.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestPlannerSettingsDefaults:
    async def test_defaults(self):
        s = Settings()
        assert s.planner_selected_location_id is None
        assert s.planner_selected_horizon_id is None
        assert s.planner_selected_rig_id is None
        assert s.planner_active_tab == "tonight"
        assert s.planner_sort_by == [PlannerSortEntry(field="primary_designation", dir="asc")]
        assert s.planner_filter_intent == []
        assert s.planner_type_filter == []
        assert s.planner_catalog_filter == []
        assert s.planner_constellation_filter == []
        assert s.planner_detail_id is None
        assert s.planner_min_hours is None
        assert s.planner_max_mag is None
        assert s.planner_min_size is None
        assert s.planner_coverage_range is None
        assert s.planner_calendar_location_id is None
        assert s.planner_calendar_horizon_id is None
        assert s.planner_calendar_rig_id is None


class TestPlannerSettingsRoundTrip:
    async def test_persist_complex_planner_state(self):
        """Round-trip every planner field including the nested SortEntry list and tuple."""
        updated = Settings(
            planner_selected_location_id=42,
            planner_selected_horizon_id=7,
            planner_selected_rig_id=3,
            planner_active_tab="anytime",
            planner_sort_by=[
                PlannerSortEntry(field="mag_v", dir="desc"),
                PlannerSortEntry(field="primary_designation", dir="asc"),
            ],
            planner_filter_intent=["Ha", "OIII"],
            planner_type_filter=["Galaxy", "PlanetaryNebula"],
            planner_catalog_filter=["NGC", "IC"],
            planner_constellation_filter=["Ori", "Sgr"],
            planner_detail_id=12345,
            planner_min_hours=3.5,
            planner_max_mag=11.0,
            planner_min_size=2.5,
            planner_coverage_range=(20.0, 80.0),
            planner_calendar_location_id=2,
            planner_calendar_horizon_id=8,
            planner_calendar_rig_id=1,
        )
        await update_settings(updated)

        reloaded = await get_settings()
        assert reloaded.planner_selected_location_id == 42
        assert reloaded.planner_selected_horizon_id == 7
        assert reloaded.planner_selected_rig_id == 3
        assert reloaded.planner_active_tab == "anytime"
        assert reloaded.planner_sort_by == [
            PlannerSortEntry(field="mag_v", dir="desc"),
            PlannerSortEntry(field="primary_designation", dir="asc"),
        ]
        assert reloaded.planner_filter_intent == ["Ha", "OIII"]
        assert reloaded.planner_type_filter == ["Galaxy", "PlanetaryNebula"]
        assert reloaded.planner_catalog_filter == ["NGC", "IC"]
        assert reloaded.planner_constellation_filter == ["Ori", "Sgr"]
        assert reloaded.planner_detail_id == 12345
        assert reloaded.planner_min_hours == 3.5
        assert reloaded.planner_max_mag == 11.0
        assert reloaded.planner_min_size == 2.5
        # tuple round-trips through JSON as a list — Pydantic re-coerces.
        assert reloaded.planner_coverage_range == (20.0, 80.0)
        assert reloaded.planner_calendar_location_id == 2
        assert reloaded.planner_calendar_horizon_id == 8
        assert reloaded.planner_calendar_rig_id == 1

    async def test_invalid_dir_falls_back_to_default(self):
        """Schema-drift safety: bad data → defaults instead of crashing."""
        # Stuff an invalid PlannerSortEntry into the DB directly and confirm
        # get_settings falls back to defaults rather than crashing.
        from nightcrate.db.session import get_db

        async with get_db() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO settings (key, value_json, updated_at)"
                ' VALUES (\'planner_sort_by\', \'[{"field":"x","dir":"bogus"}]\','
                " datetime('now'))"
            )
            await conn.commit()

        reloaded = await get_settings()
        # Falls back to the model's default sort.
        default = [PlannerSortEntry(field="primary_designation", dir="asc")]
        assert reloaded.planner_sort_by == default


class TestPlannerSettingsAPI:
    async def test_put_get_roundtrip(self, client: AsyncClient):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()

        patched = {
            **data,
            "planner_selected_rig_id": 5,
            "planner_active_tab": "wishlist",
            "planner_sort_by": [{"field": "mag_v", "dir": "desc"}],
            "planner_filter_intent": ["Ha"],
            "planner_coverage_range": [10.5, 95.0],
        }
        resp = await client.put("/api/settings", json=patched)
        assert resp.status_code == 200
        body = resp.json()
        assert body["planner_selected_rig_id"] == 5
        assert body["planner_active_tab"] == "wishlist"
        assert body["planner_sort_by"] == [{"field": "mag_v", "dir": "desc"}]
        assert body["planner_filter_intent"] == ["Ha"]
        assert body["planner_coverage_range"] == [10.5, 95.0]
