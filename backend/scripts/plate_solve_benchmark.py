"""Benchmark NightCrate's built-in plate solver against ASTAP.

This is a developer tool for the private real-image corpus.  It deliberately
runs every image/mode pair in a fresh spawned process so a crash, timeout, or
memory spike cannot contaminate the next measurement.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import multiprocessing as mp
import platform
import queue
import resource
import statistics
import subprocess
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from astropy.wcs import WCS

from nightcrate.services.star_catalog.ranges import FIELD_RANGES

TIMEOUT_SECONDS = 180.0
VALID_CATEGORIES = {
    "master",
    "sub",
    "final-xisf",
    "final-image",
    "mosaic",
    "variant-binned",
    "variant-fastintegration",
    "negative",
}
RANGE_LAYERS = {field_range.id: field_range.layers for field_range in FIELD_RANGES}
SOLUTION_FIELDS = (
    "ra_deg",
    "dec_deg",
    "cd1_1",
    "cd1_2",
    "cd2_1",
    "cd2_2",
    "crpix1",
    "crpix2",
    "image_width",
    "image_height",
    "rotation_deg",
    "pixel_scale_arcsec",
)


def _float_or_none(value: object) -> float | None:
    try:
        text = str(value).strip()
        return float(text) if text else None
    except TypeError, ValueError:
        return None


def _target_positions(path: Path) -> dict[str, tuple[float, float]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("targets", raw) if isinstance(raw, dict) else {}
    result: dict[str, tuple[float, float]] = {}
    for project, value in entries.items():
        if not isinstance(value, dict):
            continue
        ra = _float_or_none(value.get("ra", value.get("ra_deg")))
        dec = _float_or_none(value.get("dec", value.get("dec_deg")))
        if ra is not None and dec is not None:
            result[str(project)] = (ra, dec)
    return result


def _image_format(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".fit", ".fits", ".fts", ".fz"}:
        return "FITS"
    if suffix == ".xisf":
        return "XISF"
    if suffix == ".png":
        return "PNG"
    if suffix in {".jpg", ".jpeg"}:
        return "JPEG"
    if suffix in {".tif", ".tiff"}:
        return "TIFF"
    return "Other"


def _peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024**2 if platform.system() == "Darwin" else 1024)


def _solution(result: Any) -> dict[str, Any] | None:
    if not result.solved:
        return None
    data = result.model_dump()
    if any(data.get(field) is None for field in SOLUTION_FIELDS[:10]):
        return None
    return {field: data.get(field) for field in SOLUTION_FIELDS}


def _worker(job: dict[str, Any]) -> dict[str, Any]:
    # APP_DIR must be redirected before importing any service that resolves
    # star-catalog paths.  The supplied path itself is APP_DIR/star_catalogs.
    from nightcrate.core import app_config

    app_config.APP_DIR = Path(job["star_data"]).parent

    import nightcrate.services.native_solver.solve_image as solve_module
    from nightcrate.services import pixel_loader
    from nightcrate.services.native_solver.hints import SolveHints
    from nightcrate.services.native_solver.models import NullSolveReporter
    from nightcrate.services.plate_solve import read_wcs_params, run_plate_solve
    from nightcrate.services.star_catalog import ranges as range_module

    # Both solvers' modules are imported before the timer starts: the server
    # imports them once, so counting the import against one solver per image
    # would compare unlike costs.
    started = time.perf_counter()
    mode = job["mode"]
    if mode in {"native", "native-blind"}:
        selected_ranges = set(job["ranges"])
        if selected_ranges:
            selected_layers = sorted(
                {layer for range_id in selected_ranges for layer in RANGE_LAYERS[range_id]}
            )

            def selected_ranges_fn() -> set[str]:
                return set(selected_ranges)

            def selected_layers_fn() -> list[str]:
                return list(selected_layers)

            range_module.built_ranges = selected_ranges_fn
            range_module.built_layers = selected_layers_fn
            solve_module.built_ranges = selected_ranges_fn
            solve_module.built_layers = selected_layers_fn
        if mode == "native-blind":

            def no_hints(
                cards: list[dict],
                *,
                image_height: int,
                ra_hint: float | None,
                dec_hint: float | None,
                scale_hint_arcsec: float | None = None,
                fov_hint: float | None,
                ignore_position: bool = False,
                ignore_scale: bool = False,
            ) -> SolveHints:
                del (
                    cards,
                    image_height,
                    ra_hint,
                    dec_hint,
                    scale_hint_arcsec,
                    fov_hint,
                    ignore_position,
                    ignore_scale,
                )
                return SolveHints()

            solve_module.hints_for = no_hints
        result = solve_module.solve_image(
            job["image_path"],
            0,
            ra_hint=job["target_ra"] if mode == "native" else None,
            dec_hint=job["target_dec"] if mode == "native" else None,
            fov_hint=None,
            cancel=threading.Event(),
            reporter=NullSolveReporter(),
        )
    else:
        result = asyncio.run(
            run_plate_solve(
                job["astap"],
                job["image_path"],
                ra_hint=job["target_ra"],
                dec_hint=job["target_dec"],
                fov_hint=None,
                timeout=int(TIMEOUT_SECONDS),
            )
        )

    elapsed = time.perf_counter() - started
    try:
        source, file_type, image_index = pixel_loader.resolve(job["image_path"])
        header = read_wcs_params(source, file_type, image_index, 0)
    except OSError, TypeError, ValueError:
        header = None
    return {
        "solved": result.solved,
        "failure_reason": result.failure_reason
        or result.error_message
        or (None if result.solved else "unsolved"),
        "solve_path": result.solve_path,
        "scale_stage": result.scale_stage,
        "seconds": elapsed,
        "peak_rss_mb": _peak_rss_mb(),
        "solution": _solution(result),
        "header_wcs": header.model_dump() if header is not None else None,
    }


def _worker_entry(job: dict[str, Any], output: Any) -> None:
    try:
        output.put({"ok": True, "result": _worker(job)})
    except BaseException as exc:  # noqa: BLE001 - crashes become benchmark rows
        output.put({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def _sample_process_rss_mb(pid: int) -> float | None:
    try:
        completed = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
        return float(completed.stdout.strip()) / 1024 if completed.stdout.strip() else None
    except OSError, subprocess.SubprocessError, ValueError:
        return None


def _run_isolated(job: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    context = mp.get_context("spawn")
    output = context.Queue()
    process = context.Process(target=_worker_entry, args=(job, output))
    process.start()
    deadline = time.monotonic() + TIMEOUT_SECONDS
    next_rss_sample = 0.0
    sampled_peak = 0.0
    while process.is_alive() and time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_rss_sample:
            rss = _sample_process_rss_mb(process.pid)
            sampled_peak = max(sampled_peak, rss or 0.0)
            next_rss_sample = now + 1.0
        process.join(0.2)
    if process.is_alive():
        process.terminate()
        process.join(5)
        return {
            "solved": False,
            "failure_reason": "child process timeout",
            "solve_path": None,
            "scale_stage": None,
            "seconds": TIMEOUT_SECONDS,
            "peak_rss_mb": sampled_peak or None,
            "solution": None,
            "header_wcs": None,
        }
    try:
        message = output.get(timeout=1)
    except queue.Empty:
        return {
            "solved": False,
            "failure_reason": f"child process exited with status {process.exitcode}",
            "solve_path": None,
            "scale_stage": None,
            "seconds": time.perf_counter() - started,
            "peak_rss_mb": sampled_peak or None,
            "solution": None,
            "header_wcs": None,
        }
    finally:
        output.close()
    if not message["ok"]:
        return {
            "solved": False,
            "failure_reason": message["error"],
            "solve_path": None,
            "scale_stage": None,
            "seconds": time.perf_counter() - started,
            "peak_rss_mb": sampled_peak or None,
            "solution": None,
            "header_wcs": None,
        }
    result = message["result"]
    result["peak_rss_mb"] = max(sampled_peak, result.get("peak_rss_mb") or 0.0)
    if result.get("seconds") is None:
        result["seconds"] = time.perf_counter() - started
    return result


def _as_wcs(solution: dict[str, Any]) -> tuple[WCS, np.ndarray, int, int]:
    if "ra_deg" in solution:
        ra, dec = solution["ra_deg"], solution["dec_deg"]
        width, height = solution["image_width"], solution["image_height"]
    else:
        ra, dec = solution["crval1"], solution["crval2"]
        width, height = solution["naxis1"], solution["naxis2"]
    cd = np.array(
        [
            [solution["cd1_1"], solution["cd1_2"]],
            [solution["cd2_1"], solution["cd2_2"]],
        ],
        dtype=float,
    )
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.wcs.crval = [float(ra), float(dec)]
    wcs.wcs.crpix = [float(solution["crpix1"]), float(solution["crpix2"])]
    wcs.wcs.cd = cd
    wcs.array_shape = (int(height), int(width))
    return wcs, cd, int(width), int(height)


def _comparison(candidate: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    candidate_wcs, candidate_cd, _, _ = _as_wcs(candidate)
    reference_wcs, reference_cd, width, height = _as_wcs(reference)
    xs = np.linspace(0.05 * (width - 1), 0.95 * (width - 1), 7)
    ys = np.linspace(0.05 * (height - 1), 0.95 * (height - 1), 7)
    xx, yy = np.meshgrid(xs, ys)
    sky = reference_wcs.pixel_to_world(xx.ravel(), yy.ravel())
    candidate_x, candidate_y = candidate_wcs.world_to_pixel(sky)
    distances = np.hypot(candidate_x - xx.ravel(), candidate_y - yy.ravel())
    finite = bool(np.all(np.isfinite(distances)))
    invalid_distance = 10.0 * math.hypot(width, height)
    median = float(np.median(distances)) if finite else invalid_distance
    parity_equal = bool(
        np.sign(np.linalg.det(candidate_cd)) == np.sign(np.linalg.det(reference_cd))
    )
    wrong = not finite or not parity_equal or median > 0.01 * math.hypot(width, height)
    return {
        "grid_median_px": median,
        "grid_max_px": float(np.max(distances)) if finite else invalid_distance,
        "parity_equal": parity_equal,
        "wrong": wrong,
        "imprecise": bool(not wrong and median > 2.0),
    }


def _rotation(solution: dict[str, Any]) -> float:
    return math.degrees(math.atan2(-solution["cd1_2"], solution["cd2_2"]))


def _rotation_difference(first: dict[str, Any], second: dict[str, Any]) -> float:
    return abs((_rotation(first) - _rotation(second) + 180.0) % 360.0 - 180.0)


def _target_in_field(
    solution: dict[str, Any], target_ra: float | None, target_dec: float | None
) -> bool | None:
    if target_ra is None or target_dec is None:
        return None
    wcs, _, width, height = _as_wcs(solution)
    x, y = wcs.world_to_pixel_values(target_ra, target_dec)
    return bool(np.isfinite(x) and np.isfinite(y) and 0 <= x < width and 0 <= y < height)


def _add_comparisons(rows: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["file"]].append(row)
    for group in grouped.values():
        astap = next((row for row in group if row["mode"] == "astap" and row.get("solution")), None)
        header = next((row.get("header_wcs") for row in group if row.get("header_wcs")), None)
        header_suspect = bool(
            astap
            and header
            and np.sign(np.linalg.det(_as_wcs(astap["solution"])[1]))
            != np.sign(np.linalg.det(_as_wcs(header)[1]))
        )
        for row in group:
            row["reference_suspect"] = header_suspect
            row["verified"] = False
            row["wrong"] = False
            row["imprecise"] = False
            row["target_in_field"] = None
            solution = row.get("solution")
            if solution is None:
                continue
            row["target_in_field"] = _target_in_field(
                solution, row.get("target_ra"), row.get("target_dec")
            )
            if row["category"] == "negative":
                continue
            reference: dict[str, Any] | None = None
            reference_name: str | None = None
            if row["mode"].startswith("native") and astap is not None:
                reference, reference_name = astap["solution"], "astap"
            elif header is not None and not (row["mode"] == "astap" and header_suspect):
                reference, reference_name = header, "header"
            if reference is not None:
                comparison = _comparison(solution, reference)
                row["reference"] = reference_name
                row["comparison"] = comparison
                row["verified"] = True
                row["wrong"] = comparison["wrong"]
                row["imprecise"] = comparison["imprecise"]
            if row["mode"].startswith("native") and astap is not None:
                row["rotation_difference_deg"] = _rotation_difference(solution, astap["solution"])


def _percentile(values: list[float], percentile: float) -> float | None:
    return float(np.percentile(values, percentile)) if values else None


def _fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _bar_line(name: str, passed: bool, detail: str) -> str:
    return f"- **{'PASS' if passed else 'FAIL'} — {name}:** {detail}"


def _summary(rows: list[dict[str, Any]]) -> tuple[str, bool]:
    nonnegative_files = sorted({row["file"] for row in rows if row["category"] != "negative"})
    by_key = {(row["file"], row["mode"]): row for row in rows}
    native_rows = [by_key.get((name, "native")) for name in nonnegative_files]
    astap_rows = [by_key.get((name, "astap")) for name in nonnegative_files]
    rate_available = all(native_rows) and all(astap_rows) and bool(nonnegative_files)
    native_solved = sum(bool(row and row["solved"]) for row in native_rows)
    astap_solved = sum(bool(row and row["solved"]) for row in astap_rows)
    rate_pass = rate_available and native_solved >= astap_solved

    paired = [
        (native, astap)
        for native, astap in zip(native_rows, astap_rows, strict=True)
        if native and astap and native["solved"] and astap["solved"]
    ]
    native_times = [
        float(native["seconds"]) for native, _ in paired if native["seconds"] is not None
    ]
    astap_times = [float(astap["seconds"]) for _, astap in paired if astap["seconds"] is not None]
    time_available = bool(paired) and len(native_times) == len(paired) == len(astap_times)
    native_median = statistics.median(native_times) if native_times else None
    astap_median = statistics.median(astap_times) if astap_times else None
    time_pass = bool(
        time_available
        and native_median is not None
        and astap_median is not None
        and native_median <= astap_median
    )

    blind = [
        row
        for row in rows
        if row["mode"] == "native-blind" and row["category"] in {"sub", "master"}
    ]
    blind_times = [float(row["seconds"]) for row in blind if row["seconds"] is not None]
    blind_available = bool(blind) and len(blind_times) == len(blind)
    blind_median = statistics.median(blind_times) if blind_times else None
    blind_p95 = _percentile(blind_times, 95)
    blind_median_pass = bool(blind_available and blind_median is not None and blind_median <= 3.0)
    blind_p95_pass = bool(blind_available and blind_p95 is not None and blind_p95 <= 10.0)

    wrong = sum(bool(row.get("verified") and row.get("wrong")) for row in rows)
    negative_solved = sum(bool(row["solved"]) for row in rows if row["category"] == "negative")
    all_passed = all(
        (rate_pass, time_pass, blind_median_pass, blind_p95_pass, wrong == 0, negative_solved == 0)
    )
    lines = [
        "# Plate-solver benchmark summary",
        "",
        "## Default-solver bar",
        "",
        _bar_line(
            "Solve rate",
            rate_pass,
            f"native {native_solved}/{len(nonnegative_files)}; "
            f"ASTAP {astap_solved}/{len(nonnegative_files)}"
            if rate_available
            else "requires both native and ASTAP modes over the non-negative corpus",
        ),
        _bar_line(
            "Median time on images both solve",
            time_pass,
            f"native {_fmt(native_median)} s; ASTAP {_fmt(astap_median)} s; {len(paired)} images"
            if time_available
            else "no complete native/ASTAP solved pairs",
        ),
        _bar_line(
            "Fully blind median ≤ 3 s",
            blind_median_pass,
            f"{_fmt(blind_median)} s across {len(blind)} subs and masters"
            if blind_available
            else "native-blind measurements are incomplete",
        ),
        _bar_line(
            "Fully blind P95 ≤ 10 s",
            blind_p95_pass,
            f"{_fmt(blind_p95)} s across {len(blind)} subs and masters"
            if blind_available
            else "native-blind measurements are incomplete",
        ),
        _bar_line(
            "Zero wrong verified solutions in any mode",
            wrong == 0,
            f"{wrong} wrong among verified rows",
        ),
        _bar_line("Zero negative images solved", negative_solved == 0, f"{negative_solved} solved"),
        "",
        f"## Overall: {'PASS' if all_passed else 'FAIL'}",
        "",
        "Failures count at elapsed time only for the fully blind median and P95. "
        "The native/ASTAP median excludes failures, as fixed in spec §11.2.",
        "",
        "## Counts by category",
        "",
        "| Category | Mode | Attempted | Solved | Wrong | Imprecise |",
        "|---|---|---:|---:|---:|---:|",
    ]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["category"], row["mode"])].append(row)
    for (category, mode), group in sorted(groups.items()):
        lines.append(
            f"| {category} | {mode} | {len(group)} | "
            f"{sum(bool(row['solved']) for row in group)} | "
            f"{sum(bool(row.get('wrong')) for row in group)} | "
            f"{sum(bool(row.get('imprecise')) for row in group)} |"
        )

    unverified = [row for row in rows if row["solved"] and not row.get("verified")]
    lines.extend(
        [
            "",
            "## Unverified solves",
            "",
        ]
    )
    if unverified:
        lines.extend(
            [
                "| File | Mode | Target in field |",
                "|---|---|---|",
            ]
        )
        for row in unverified:
            target_check = row.get("target_in_field")
            label = "unknown" if target_check is None else str(bool(target_check)).lower()
            lines.append(f"| {row['file']} | {row['mode']} | {label} |")
    else:
        lines.append("None.")

    lines.extend(
        [
            "",
            "## Counts by format",
            "",
            "| Format | Mode | Attempted | Solved | Wrong |",
            "|---|---|---:|---:|---:|",
        ]
    )
    formats: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        formats[(row["format"], row["mode"])].append(row)
    for (format_name, mode), group in sorted(formats.items()):
        lines.append(
            f"| {format_name} | {mode} | {len(group)} | "
            f"{sum(bool(row['solved']) for row in group)} | "
            f"{sum(bool(row.get('wrong')) for row in group)} |"
        )

    rotations = [
        float(row["rotation_difference_deg"])
        for row in rows
        if row.get("rotation_difference_deg") is not None
    ]
    grid = [
        float(row["comparison"]["grid_median_px"])
        for row in rows
        if row["mode"].startswith("native")
        and row.get("reference") == "astap"
        and row.get("comparison")
    ]
    lines.extend(
        [
            "",
            "## Native against ASTAP",
            "",
            "- Rotation difference: median "
            f"{_fmt(statistics.median(rotations) if rotations else None)}°, "
            f"maximum {_fmt(max(rotations) if rotations else None)}° ({len(rotations)} images).",
            f"- Grid distance: median {_fmt(statistics.median(grid) if grid else None)} px, "
            f"P90 {_fmt(_percentile(grid, 90))} px ({len(grid)} images).",
            "",
            "## Peak child RSS",
            "",
            "| Mode | Maximum MB |",
            "|---|---:|",
        ]
    )
    for mode in sorted({row["mode"] for row in rows}):
        values = [
            float(row["peak_rss_mb"])
            for row in rows
            if row["mode"] == mode and row.get("peak_rss_mb") is not None
        ]
        lines.append(f"| {mode} | {_fmt(max(values) if values else None, 1)} |")
    suspect = len({row["file"] for row in rows if row.get("reference_suspect")})
    lines.extend(["", f"Stored-header references marked suspect: {suspect}.", ""])
    return "\n".join(lines), all_passed


def _load_manifest(corpus: Path) -> list[dict[str, str]]:
    with (corpus / "manifest.csv").open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    required = {"file", "category", "rig", "project"}
    missing = required - set(rows[0] if rows else ())
    if missing:
        raise ValueError(f"manifest.csv is missing columns: {', '.join(sorted(missing))}")
    invalid = sorted({row["category"] for row in rows} - VALID_CATEGORIES)
    if invalid:
        raise ValueError(f"manifest.csv has unknown categories: {', '.join(invalid)}")
    return rows


def _inside_repo(path: Path, repo: Path) -> bool:
    return path == repo or repo in path.parents


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark native plate solving against ASTAP")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--star-data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--astap", type=Path)
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=("native", "native-blind", "astap"),
        default=("native", "native-blind", "astap"),
    )
    parser.add_argument("--images", nargs="+")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--ranges", nargs="+", choices=tuple(RANGE_LAYERS))
    args = parser.parse_args(argv)

    repo = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if _inside_repo(output, repo):
        parser.error(f"--output must be outside the repository ({repo})")
    if "astap" in args.modes and args.astap is None:
        parser.error("--astap is required when astap mode is selected")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    corpus = args.corpus.resolve(strict=True)
    targets = _target_positions(args.targets.resolve(strict=True))
    star_data = args.star_data.resolve(strict=True)
    manifest = _load_manifest(corpus)
    if args.images:
        tokens = [token.casefold() for token in args.images]
        manifest = [
            row
            for row in manifest
            if any(
                token in " ".join((row["file"], row["project"], row["rig"])).casefold()
                for token in tokens
            )
        ]
    if args.limit is not None:
        manifest = manifest[: args.limit]

    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for item in manifest:
        relative = item["file"]
        image = Path(relative)
        image_path = image if image.is_absolute() else corpus / image
        header_position = (
            _float_or_none(item.get("header_ra")),
            _float_or_none(item.get("header_dec")),
        )
        project_target = targets.get(item["project"])
        target = None if all(value is not None for value in header_position) else project_target
        for mode in args.modes:
            job = {
                "mode": mode,
                "image_path": str(image_path),
                "star_data": str(star_data),
                "astap": str(args.astap) if args.astap is not None else None,
                "target_ra": target[0] if target else None,
                "target_dec": target[1] if target else None,
                "ranges": args.ranges or [],
            }
            measured = _run_isolated(job)
            rows.append(
                {
                    "mode": mode,
                    "file": relative,
                    "category": item["category"],
                    "format": _image_format(relative),
                    "rig": item["rig"],
                    "project": item["project"],
                    "target_ra": project_target[0] if project_target else None,
                    "target_dec": project_target[1] if project_target else None,
                    **measured,
                }
            )

    _add_comparisons(rows)
    with (output / "results.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    summary, _passed = _summary(rows)
    (output / "summary.md").write_text(summary, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
