from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import numpy as np
from numpy.typing import NDArray

from nightcrate.services.plate_solve_models import AttemptOutcome, SolveAttempt, SolveStep
from nightcrate.services.star_catalog.models import StarCatalog as StarCatalog

FloatArray = NDArray[np.float64]


class SolveReporter(Protocol):
    def plan(self, steps: list[SolveStep]) -> None: ...

    def start(self, attempt: SolveAttempt) -> None: ...

    def searched(self, layers: list[str], ranges: list[str]) -> None: ...

    def set_sources(
        self,
        position_source: Literal["request", "header", "none"],
        scale_source: Literal["request", "header", "none"],
    ) -> None: ...

    def finish(self, outcome: AttemptOutcome, *, detail: str | None = None) -> None: ...


class NullSolveReporter:
    def plan(self, steps: list[SolveStep]) -> None:
        del steps

    def start(self, attempt: SolveAttempt) -> None:
        del attempt

    def searched(self, layers: list[str], ranges: list[str]) -> None:
        del layers, ranges

    def set_sources(
        self,
        position_source: Literal["request", "header", "none"],
        scale_source: Literal["request", "header", "none"],
    ) -> None:
        del position_source, scale_source

    def finish(self, outcome: AttemptOutcome, *, detail: str | None = None) -> None:
        del outcome, detail


@dataclass(frozen=True)
class DetectedStars:
    x: FloatArray
    y: FloatArray
    flux: FloatArray
    fwhm: FloatArray
    width: int
    height: int

    def __post_init__(self) -> None:
        n = len(self.x)
        if any(a.shape != (n,) for a in (self.x, self.y, self.flux, self.fwhm)):
            raise ValueError("detected-star columns must be one-dimensional and equally sized")

    def __len__(self) -> int:
        return len(self.x)

    @property
    def xy(self) -> FloatArray:
        return np.column_stack((self.x, self.y))


@dataclass(frozen=True)
class TanWCS:
    crval_ra: float
    crval_dec: float
    cd: FloatArray
    width: int
    height: int

    def __post_init__(self) -> None:
        if np.asarray(self.cd).shape != (2, 2):
            raise ValueError("CD must be a 2x2 matrix")

    @property
    def crpix(self) -> tuple[float, float]:
        return ((self.width + 1.0) / 2.0, (self.height + 1.0) / 2.0)

    @property
    def center_pixel(self) -> FloatArray:
        return np.array([(self.width - 1.0) / 2.0, (self.height - 1.0) / 2.0])

    @property
    def scale_arcsec(self) -> float:
        return float(np.sqrt(abs(np.linalg.det(self.cd))) * 3600.0)

    @property
    def parity(self) -> int:
        return 1 if np.linalg.det(self.cd) >= 0 else -1

    @property
    def rotation_deg(self) -> float:
        # NightCrate's displayed ASTAP/CROTA2 convention.
        return float(np.degrees(np.arctan2(self.cd[1, 0], self.cd[1, 1])) % 360.0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "crval1": self.crval_ra,
            "crval2": self.crval_dec,
            "crpix1": self.crpix[0],
            "crpix2": self.crpix[1],
            "cd1_1": float(self.cd[0, 0]),
            "cd1_2": float(self.cd[0, 1]),
            "cd2_1": float(self.cd[1, 0]),
            "cd2_2": float(self.cd[1, 1]),
            "naxis1": self.width,
            "naxis2": self.height,
        }


@dataclass(frozen=True)
class SolverConfig:
    code_tolerance: float = 0.025
    code_tolerance_min: float = 0.0025
    code_tolerance_max: float = 0.010
    depth_passes: tuple[int, ...] = (30, 60, 120, 240)
    blind_max_stars: int = 80
    image_max_b_per_a: int = 4
    include_all_depth_pass: bool = True
    quad_method: str = "diameter"
    catalog_depth_multiple: float = 1.0
    initial_search_radius_deg: float = 0.5
    radius_growth: float = 2.0
    catalog_cell_overlap: bool = True
    verification_catalog_ratio: float = 1.5
    image_quad_min_fraction: float = 0.08
    image_quad_max_fraction: float = 0.75
    max_image_quads: int = 4_000
    max_catalog_quads_per_cell: int = 2_000
    quad_interior_stars: int = 12
    quads_per_diameter: int = 8
    max_code_matches: int = 2_000
    max_candidates: int = 300
    max_verify_per_layer: int = 48
    initial_match_radius_px: float = 4.0
    final_match_radius_px: float = 2.0
    position_sigma_px: float = 1.0
    true_match_probability: float = 0.75
    min_matches: int = 10
    min_quadrants: int = 3
    # Blind search tests orders of magnitude more hypotheses than a hinted
    # search, so the acceptance threshold is a global phase-2 decision.
    log_odds_threshold: float = float(np.log(1e18))
    max_axis_scale_ratio: float = 1.05
    max_axis_nonorthogonality_deg: float = 3.0
    scale_min_arcsec: float = 0.2
    scale_max_arcsec: float = 30.0
    scale_tolerance: float = 0.15
    max_solve_seconds: float = 20.0


@dataclass(frozen=True)
class BlindSolverConfig(SolverConfig):
    """Blind-search settings, kept separate from hinted-solver defaults."""

    code_tolerance: float = 0.010
    depth_passes: tuple[int, ...] = (30, 60, 80)
    true_match_probability: float = 0.65
    min_matches: int = 12
    max_axis_nonorthogonality_deg: float = 0.2
    seed_match_radius_px: float = 12.0


@dataclass
class SolveOutcome:
    status: Literal["solved", "not_solved", "ambiguous", "time_limit", "cancelled"]
    reason: str
    wcs: TanWCS | None = None
    log_odds: float = float("-inf")
    matched_count: int = 0
    detected_count: int = 0
    rms_px: float | None = None
    rms_arcsec: float | None = None
    timings: dict[str, float] = field(default_factory=dict)
    candidates_tested: int = 0
    search_radius_deg: float | None = None
    depth: int | None = None
    quad_caps: list[str] = field(default_factory=list)
    scale_stage: str | None = None
    scale_stages_tried: list[str] = field(default_factory=list)
    ambiguous_wcs: list[TanWCS] = field(default_factory=list)
    max_false_log_odds: float = float("-inf")
    time_budget_hit: bool = False
    fitted_detection_indices: list[int] = field(default_factory=list)
    rejection_counts: dict[str, int] = field(default_factory=dict)
    candidate_rank: int | None = None
    candidate_agreement: int | None = None

    @property
    def solved(self) -> bool:
        return self.status == "solved" and self.wcs is not None

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status,
            "solved": self.solved,
            "reason": self.reason,
            "log_odds": self.log_odds,
            "matched_count": self.matched_count,
            "detected_count": self.detected_count,
            "rms_px": self.rms_px,
            "rms_arcsec": self.rms_arcsec,
            "timings": self.timings,
            "candidates_tested": self.candidates_tested,
            "search_radius_deg": self.search_radius_deg,
            "depth": self.depth,
            "quad_caps": self.quad_caps,
            "scale_stage": self.scale_stage,
            "scale_stages_tried": self.scale_stages_tried,
            "max_false_log_odds": self.max_false_log_odds,
            "time_budget_hit": self.time_budget_hit,
            "fitted_detection_indices": self.fitted_detection_indices,
            "rejection_counts": self.rejection_counts,
            "candidate_rank": self.candidate_rank,
            "candidate_agreement": self.candidate_agreement,
        }
        if self.wcs:
            data.update(self.wcs.as_dict())
            data.update(
                scale_arcsec=self.wcs.scale_arcsec,
                parity=self.wcs.parity,
                rotation_deg=self.wcs.rotation_deg,
            )
        if self.ambiguous_wcs:
            data["solutions"] = [solution.as_dict() for solution in self.ambiguous_wcs]
        return data


# The ported prototype used this name internally. Keep the alias local to the
# solver package while exposing the product-facing SolveOutcome interface.
SolveResult = SolveOutcome
