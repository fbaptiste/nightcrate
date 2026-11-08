"""Build an isolated synthetic gallery workspace from a catalog-bearing database."""

from __future__ import annotations

import argparse
import asyncio
import random
import sqlite3
import sys
from pathlib import Path

import aiosqlite
from PIL import Image, ImageDraw

from nightcrate.core import app_config
from nightcrate.services.project_images import (
    CROP_SIZES,
    crop_path,
    fit_box,
    generate_cropped_thumbnail,
)

_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))
from tests.gallery_library import populate_gallery_projects  # noqa: E402


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _validate_paths(source_db: Path, dest: Path) -> tuple[Path, Path]:
    try:
        source = source_db.expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"Source database does not exist: {source_db}") from exc
    if not source.is_file():
        raise ValueError(f"Source database is not a file: {source}")

    destination = dest.expanduser().resolve(strict=False)
    if destination.exists():
        if not destination.is_dir():
            raise ValueError(f"Destination is not a directory: {destination}")
        if any(destination.iterdir()):
            raise ValueError(f"Destination must be new or empty: {destination}")
    elif not destination.parent.is_dir():
        raise ValueError(f"Destination parent must already exist: {destination.parent}")

    config = app_config.load_config()
    protected = [app_config.APP_DIR.resolve(strict=False), source.parent]
    protected.extend(Path(path).expanduser().resolve(strict=False) for path in config.databases)
    for path in protected:
        if _overlaps(destination, path):
            raise ValueError(f"Destination must not contain or be inside protected path: {path}")
    return source, destination


def _star_field(size: tuple[int, int], seed: int) -> Image.Image:
    rng = random.Random(seed)
    width, height = size
    image = Image.new("RGB", size, (3, 7, 18))
    draw = ImageDraw.Draw(image)
    for _ in range(max(100, width * height // 3500)):
        x = rng.randrange(width)
        y = rng.randrange(height)
        radius = rng.choices((1, 2, 3), weights=(85, 13, 2), k=1)[0]
        warmth = rng.randrange(180, 256)
        colour = (warmth, min(255, warmth + rng.randrange(0, 35)), 255)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=colour)
    # A restrained synthetic nebula makes image aspect and containment obvious.
    for radius in range(min(width, height) // 3, 10, -12):
        shade = max(10, 70 - radius // 10)
        cx = width * 0.58
        cy = height * 0.46
        draw.ellipse(
            (cx - radius * 1.4, cy - radius, cx + radius * 1.4, cy + radius),
            outline=(shade, 30, min(130, shade + 45)),
            width=3,
        )
    return image


def _write_renditions(dest: Path, project_id: int, image_id: int, index: int, seed: int) -> None:
    aspect_sizes = ((1200, 900), (900, 1200), (1000, 1000), (1400, 788))
    base = _star_field(aspect_sizes[index % len(aspect_sizes)], seed * 100_003 + index)
    image_dir = dest / "project_data" / str(project_id) / f"img_{image_id}"
    image_dir.mkdir(parents=True, exist_ok=True)
    variants = {"thumb_sm": 180, "thumb_md": 400, "thumb_lg": 800, "full": 1600}
    for name, long_edge in variants.items():
        rendered = base.copy()
        rendered.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
        rendered.save(image_dir / f"{name}.jpg", "JPEG", quality=88, optimize=True)


def _crop_frame(width: int, height: int, index: int) -> tuple[float, float, float, float]:
    """Choose a deterministic whole, zoomed, or mat-crossing 4:3 frame."""
    fit_x, fit_y, fit_w, fit_h = fit_box(width, height)
    mode = index % 3
    if mode == 0:
        return fit_x, fit_y, fit_w, fit_h

    scale = 0.65 if mode == 1 else 0.7
    crop_w = fit_w * scale
    crop_h = fit_h * scale
    if mode == 1:
        return (
            fit_x + (fit_w - crop_w) / 2,
            fit_y + (fit_h - crop_h) / 2,
            crop_w,
            crop_h,
        )

    # Anchor the frame to a mat edge. For portrait and square sources this
    # deliberately includes the left mat; landscapes include the top mat.
    if width <= height:
        return fit_x, fit_y + (fit_h - crop_h) / 2, crop_w, crop_h
    return fit_x + (fit_w - crop_w) / 2, fit_y, crop_w, crop_h


async def _write_crops(
    destination_db: Path,
    dest: Path,
    rendered: list[tuple[int, int]],
) -> None:
    """Give about a third of rendered projects all three framed sizes."""
    async with aiosqlite.connect(destination_db) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        for framed_index, (project_id, image_id) in enumerate(rendered[::3]):
            full_path = dest / "project_data" / str(project_id) / f"img_{image_id}" / "full.jpg"
            with Image.open(full_path) as source:
                frame = _crop_frame(*source.size, framed_index)
            for size in CROP_SIZES:
                cursor = await conn.execute(
                    """
                    INSERT INTO project_thumbnail (
                        project_id, size, source_image_id, crop_x, crop_y, crop_w, crop_h
                    ) VALUES (?, ?, NULL, ?, ?, ?, ?)
                    """,
                    (project_id, size, *frame),
                )
                output = crop_path(dest / "project_data" / str(project_id), size, cursor.lastrowid)
                generate_cropped_thumbnail(str(full_path), *frame, output, size)
        await conn.commit()


def _backup_database(source: Path, destination: Path) -> None:
    """Copy a live SQLite database, including committed WAL contents, read-only."""
    source_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    destination_conn = sqlite3.connect(destination)
    try:
        source_conn.backup(destination_conn)
    finally:
        destination_conn.close()
        source_conn.close()


async def _build(source: Path, dest: Path, projects: int, seed: int) -> None:
    destination_db = dest / app_config.DB_FILENAME
    _backup_database(source, destination_db)
    async with aiosqlite.connect(destination_db) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        cursor = await conn.execute("SELECT id FROM dso WHERE active = 1 ORDER BY id")
        active_ids = [int(row["id"]) for row in await cursor.fetchall()]
        if len(active_ids) < 8:
            raise ValueError("Source database needs at least 8 active DSOs")
        rng = random.Random(seed)
        chosen = rng.sample(active_ids, min(40, len(active_ids)))
        summary = await populate_gallery_projects(
            conn,
            chosen,
            n_projects=projects,
            seed=seed,
        )
        for project_id, image_id in summary.main_images.items():
            full_path = dest / "project_data" / str(project_id) / f"img_{image_id}" / "full.jpg"
            await conn.execute(
                "UPDATE project_image SET file_path = ? WHERE id = ?",
                (str(full_path), image_id),
            )
        await conn.commit()

    # Five deliberately broken previews exercise the gallery's missing-rendition state.
    rendered = list(summary.main_images.items())[5:]
    for index, (project_id, image_id) in enumerate(rendered):
        _write_renditions(dest, project_id, image_id, index, seed)
    await _write_crops(destination_db, dest, rendered)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--projects", type=int, default=500)
    parser.add_argument("--seed", type=int, default=46)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.projects < 0:
        raise SystemExit("--projects must be non-negative")
    try:
        source, dest = _validate_paths(args.source_db, args.dest)
        dest.mkdir(exist_ok=True)
        asyncio.run(_build(source, dest, args.projects, args.seed))
    except (OSError, ValueError, aiosqlite.Error) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Synthetic gallery workspace created at {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
