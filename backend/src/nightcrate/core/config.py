"""Application settings — one row per preference in the `settings` KV table.

The Pydantic `Settings` model is the single source of truth for field names,
types, and defaults. The DB layer maps field ↔ row, serialising each value
as JSON text so composite types round-trip cleanly.
"""

import json
import logging
from collections.abc import Iterable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError

from nightcrate.db.session import get_db

logger = logging.getLogger(__name__)
_last_logged_dropped_fields: frozenset[str] = frozenset()

SLIDESHOW_SECONDS: tuple[int, ...] = (2, 3, 4, 5, 6, 8, 10, 15, 20, 30)
THRESHOLD_FIELDS = (
    "scoring_threshold_excellent",
    "scoring_threshold_good",
    "scoring_threshold_fair",
)
_WEIGHT_FIELDS = (
    "scoring_weight_observability",
    "scoring_weight_meridian",
    "scoring_weight_moon",
    "scoring_weight_frame_fit",
)


class BrowserFavorite(BaseModel):
    name: str
    path: str


class PlannerSortEntry(BaseModel):
    field: str
    dir: Literal["asc", "desc"]


PlannerTab = Literal["tonight", "anytime", "wishlist"]
FilterLine = Literal["Ha", "SII", "OIII", "L", "R", "G", "B"]


class Settings(BaseModel):
    theme: Literal["light", "dark", "browser"] = "browser"
    gallery_view: Literal["list", "small", "medium", "large"] = "medium"
    gallery_slideshow_seconds: Literal[2, 3, 4, 5, 6, 8, 10, 15, 20, 30] = 5
    messier_view: Literal["small", "medium", "large"] = "medium"
    messier_imaged_style: Literal["own", "sky"] = "own"
    messier_unimaged_style: Literal["sky", "blank"] = "sky"
    messier_show_projects: bool = False
    messier_location: Annotated[int, Field(strict=True, gt=0)] | Literal["default", "none"] = (
        "default"
    )
    messier_rig_id: int | None = None
    gpu_acceleration: bool = True
    max_worker_cores: int | None = None  # None → cpu_count - 1
    last_browse_path: str | None = None
    browser_favorites: list[BrowserFavorite] = []
    aberration_cache_ttl_days: int = 30
    weather_cache_ttl_hours: int = 6
    weather_units: Literal["metric", "imperial"] = "metric"
    # User-chosen display order for the Calculators "Clocks" view. Empty list
    # means "use the component's default order"; unknown ids are filtered on
    # the client so new clocks added later don't break stored arrays.
    calculators_clock_order: list[str] = []
    # User-chosen display order for the left-nav (drag-to-reorder). Values
    # are nav route paths (e.g., "/image-viewer", "/planner"). Home ("/")
    # is pinned at the top and is never stored here. Empty list → use the
    # default order from ``AppShell``. Same forward-compat contract as
    # ``calculators_clock_order``: unknown routes are filtered on the
    # client, missing-from-list routes are appended at the end.
    nav_order: list[str] = []
    # Target Planner filter defaults — initial slider values on the
    # planner page. The altitude floor now lives on each location as a
    # horizon (see ``location_horizon``), so there's no global flat
    # default setting anymore.
    planner_min_visibility_hours: float = 2.0
    planner_max_magnitude: float = 12.0
    planner_min_size_arcmin: float = 5.0
    # Initial bounds for the Frames-Well coverage-range slider (and
    # the default band the slider resets to when the rig changes).
    # 0-200 = no filter; 15-90 matches the old fixed "frames well"
    # bounds from the checkbox era.
    planner_frames_well_min_pct: float = 15.0
    planner_frames_well_max_pct: float = 90.0
    # Default moon-separation value for the "Best time of year" chart
    # in the planner detail panel. ``0`` ignores the moon entirely
    # (every hour above horizon during astro dark counts); larger
    # values filter out nights where the moon lands within that angle
    # of the target.
    planner_moon_sep_deg: int = 0
    # Disk budget for the HiPS/DSS2 caches. Covers both the per-DSO
    # ``APP_DIR/thumbnails/`` (list/detail/rig_framed variants) and
    # the v0.18.0 regional ``APP_DIR/sky_tiles/`` cache. 500 MB is the
    # Pass C default — the regional cache caches whole HEALPix tiles
    # shared across DSOs, so a larger budget makes the cache-reuse
    # payoff actually compound. Users on tight disks can dial down in
    # Settings; users browsing hundreds of targets can go up to 5 GB.
    thumbnail_cache_max_mb: int = 500
    # Monotonic counter appended to thumbnail URLs as ``&_g=N`` so that
    # clearing the cache invalidates any copies the user's browser HTTP
    # cache holds. Incremented by the cache-clear endpoint.
    thumbnail_cache_generation: int = 0
    # ─── Target Planner scoring (v0.21.0) ──────────────────────────
    # Feeds ``services/planner_scoring.py``. See ``docs/planner-scoring.md``.
    # Combination weights — zero removes the dimension from the geometric mean.
    scoring_weight_observability: float = 2.0
    scoring_weight_meridian: float = 1.0
    scoring_weight_moon: float = 1.5
    scoring_weight_frame_fit: float = 1.0
    # Moon sensitivity per filter line: 0 = immune, 1 = broadband-equivalent.
    scoring_moon_sensitivity_ha: float = 0.15
    scoring_moon_sensitivity_sii: float = 0.25
    scoring_moon_sensitivity_oiii: float = 0.70
    scoring_moon_sensitivity_l: float = 0.95
    scoring_moon_sensitivity_r: float = 0.55
    scoring_moon_sensitivity_g: float = 0.85
    scoring_moon_sensitivity_b: float = 1.00
    # Min-separation thresholds (deg): proximity factor interpolates
    # linearly from 0 (at moon) to 1 (at this separation or beyond).
    scoring_moon_min_sep_ha: float = 60.0
    scoring_moon_min_sep_sii: float = 60.0
    scoring_moon_min_sep_oiii: float = 90.0
    scoring_moon_min_sep_l: float = 90.0
    scoring_moon_min_sep_r: float = 60.0
    scoring_moon_min_sep_g: float = 90.0
    scoring_moon_min_sep_b: float = 90.0
    # Moon impact component weights: sky glow (global sky brightness
    # from scattered moonlight) + proximity (local gradient/glare near
    # the moon). min_sep only governs the proximity component.
    scoring_moon_sky_glow_weight: float = 0.6
    scoring_moon_proximity_weight: float = 0.4
    # Moon-impact multiplier for OCl / GCl / *Ass (cluster) targets.
    scoring_cluster_moon_modifier: float = 0.5
    # Meridian timing buffer: extends the zero point beyond the dark
    # window boundary so targets transiting just outside dark aren't
    # penalised as harshly as those transiting hours outside.
    scoring_meridian_buffer_hours: float = 2.0
    # Altitude threshold and max-airmass anchor for the observability
    # curve. Minimum 10° — below that the airmass formula produces
    # extreme values and compresses the quality gradient.
    scoring_observability_min_altitude_deg: float = 30.0
    # Frame-fit Gaussian shape.
    scoring_frame_fit_ideal_coverage_pct: float = 55.0
    scoring_frame_fit_spread: float = 35.0
    # Quality chip thresholds — validator enforces strict descending order.
    scoring_threshold_excellent: int = 80
    scoring_threshold_good: int = 60
    scoring_threshold_fair: int = 40
    # Hard gates. ``None`` on the coverage gate disables it — the
    # frame-fit Gaussian handles oversized targets gracefully on its own.
    scoring_gate_min_obs_hours: float = 1.0
    scoring_gate_max_coverage_pct: float | None = None
    # PHD2 Analyzer — per-panel pixel heights for the resizable
    # Guiding-tab dividers. Keys: ``"main"``, ``"snr"``, ``"mass"``.
    # Missing keys → fall back to the ratio-derived default height.
    # Each value clamps to its panel's default minimum.
    phd2_panel_heights: dict[str, int] = Field(default_factory=dict)
    # PHD2 Analyzer — expanded state of the per-tab "What is this
    # view?" help explainers. Keys: ``"graph"``, ``"dispersion"``,
    # ``"data"``. Missing key (or value ``False``) → explainer is
    # collapsed by default. Set to ``True`` once the user expands
    # the panel and the state should persist.
    phd2_help_expanded: dict[str, bool] = Field(default_factory=dict)
    astap_executable_path: str | None = None
    default_solver: Literal["native", "astap"] = "native"
    # ─── Target Planner UI state ───────────────────────────────────
    # Persisted across sessions so iPad/Mac/etc share the same state.
    # `searchQuery` (free-text search box) is intentionally NOT here —
    # it stays ephemeral per-session.
    planner_selected_location_id: int | None = None
    planner_selected_horizon_id: int | None = None
    planner_selected_rig_id: int | None = None
    planner_active_tab: PlannerTab = "tonight"
    planner_sort_by: list[PlannerSortEntry] = Field(
        default_factory=lambda: [PlannerSortEntry(field="primary_designation", dir="asc")]
    )
    planner_filter_intent: list[FilterLine] = Field(default_factory=list)
    planner_type_filter: list[str] = Field(default_factory=list)
    planner_catalog_filter: list[str] = Field(default_factory=list)
    planner_constellation_filter: list[str] = Field(default_factory=list)
    planner_detail_id: int | None = None
    planner_min_hours: float | None = None
    planner_max_mag: float | None = None
    planner_min_size: float | None = None
    planner_coverage_range: tuple[float, float] | None = None
    planner_calendar_location_id: int | None = None
    planner_calendar_horizon_id: int | None = None
    planner_calendar_rig_id: int | None = None

    @model_validator(mode="after")
    def _validate_scoring(self) -> Settings:
        violations = _cross_field_violations(self)
        if violations:
            if violations.issuperset(THRESHOLD_FIELDS):
                message = (
                    "scoring_threshold_excellent > scoring_threshold_good > "
                    "scoring_threshold_fair must hold"
                )
            elif "scoring_observability_min_altitude_deg" in violations:
                message = (
                    "scoring_observability_min_altitude_deg must be >= 10 "
                    "(below 10° the airmass formula produces extreme values)"
                )
            else:
                name = sorted(violations)[0]
                message = f"{name} must be non-negative"
            raise PydanticCustomError(
                "cross_field",
                message,
                {"fields": sorted(violations)},
            )
        return self


def _cross_field_violations(settings: Settings) -> frozenset[str]:
    """Return every field participating in a failed cross-field rule."""
    violations: set[str] = set()
    if not (
        settings.scoring_threshold_excellent
        > settings.scoring_threshold_good
        > settings.scoring_threshold_fair
    ):
        violations.update(THRESHOLD_FIELDS)
    if settings.scoring_observability_min_altitude_deg < 10.0:
        violations.add("scoring_observability_min_altitude_deg")
    violations.update(name for name in _WEIGHT_FIELDS if getattr(settings, name) < 0)
    return frozenset(violations)


def settings_from_rows(data: dict[str, Any]) -> tuple[Settings, frozenset[str]]:
    """Load stored values, dropping only fields that fail current validation."""
    remaining = dict(data)
    dropped: set[str] = set()
    for _ in range(3):
        try:
            settings = Settings(**remaining)
            dropped_fields = frozenset(dropped)
            _log_dropped_fields(dropped_fields)
            return settings, dropped_fields
        except ValidationError as exc:
            invalid: set[str] = set()
            for error in exc.errors():
                if error["type"] == "cross_field":
                    invalid.update(error.get("ctx", {}).get("fields", ()))
                elif error["loc"]:
                    invalid.add(str(error["loc"][0]))
            invalid.intersection_update(remaining)
            if not invalid:
                break
            dropped.update(invalid)
            for key in invalid:
                remaining.pop(key, None)

    dropped.update(remaining)
    dropped_fields = frozenset(dropped)
    _log_dropped_fields(dropped_fields)
    return Settings(), dropped_fields


def _log_dropped_fields(dropped: frozenset[str]) -> None:
    """Warn once for each distinct damaged-field set seen consecutively.

    A clean load resets the memory, so damage that returns after a repair is
    reported again.
    """
    global _last_logged_dropped_fields
    if dropped and dropped != _last_logged_dropped_fields:
        logger.warning("[settings] ignored invalid stored fields: %s", sorted(dropped))
    _last_logged_dropped_fields = dropped


def _decode_rows(rows: Iterable[Any]) -> dict[str, Any]:
    """Decode known settings rows, skipping invalid JSON and unknown keys."""
    known = set(Settings.model_fields)
    data: dict[str, Any] = {}
    for row in rows:
        key = row["key"]
        if key not in known:
            continue
        try:
            data[key] = json.loads(row["value_json"])
        except ValueError:
            continue
    return data


async def get_settings() -> Settings:
    """Load settings from the DB. Unknown rows are ignored; missing rows fall
    back to the Pydantic defaults. Rows whose JSON fails to decode are skipped
    (the field keeps its default)."""
    async with get_db() as conn:
        cursor = await conn.execute("SELECT key, value_json FROM settings")
        rows = await cursor.fetchall()

    settings, _dropped = settings_from_rows(_decode_rows(rows))
    return settings


class SettingsPatchError(ValueError):
    """A partial settings update could not be safely applied."""


async def update_settings_partial(patch: dict[str, Any]) -> Settings:
    """Validate and persist only the supplied settings fields atomically."""
    known = set(Settings.model_fields)
    unknown = sorted(set(patch) - known)
    if unknown:
        raise SettingsPatchError(f"Unknown setting(s): {', '.join(unknown)}")

    async with get_db() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = await conn.execute("SELECT key, value_json FROM settings")
            rows = await cursor.fetchall()
            current, dropped = settings_from_rows(_decode_rows(rows))
            merged = current.model_dump()
            merged.update(patch)
            try:
                saved = Settings(**merged)
            except ValidationError as exc:
                messages = "; ".join(error["msg"] for error in exc.errors())
                raise SettingsPatchError(messages) from exc

            payload = saved.model_dump()
            write_keys = set(patch)
            if write_keys.intersection(THRESHOLD_FIELDS) and dropped.intersection(THRESHOLD_FIELDS):
                write_keys.update(THRESHOLD_FIELDS)
            for key in sorted(write_keys):
                await conn.execute(
                    """
                    INSERT INTO settings (key, value_json, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value_json = excluded.value_json,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (key, json.dumps(payload[key])),
                )
            await conn.commit()
            return saved
        except BaseException:
            await conn.rollback()
            raise


async def update_settings(updated: Settings) -> Settings:
    """Persist the full Settings object. Each field becomes one KV row via
    upsert; `updated_at` is refreshed on every affected row."""
    payload = updated.model_dump()
    async with get_db() as conn:
        for key, value in payload.items():
            await conn.execute(
                """
                INSERT INTO settings (key, value_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, json.dumps(value)),
            )
        await conn.commit()
    return updated
