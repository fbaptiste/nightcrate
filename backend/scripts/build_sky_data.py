"""Build NightCrate's compact, licensed sky data.

Fetch d3-celestial 0.7.35, HYG v4.4, Stellarium's modern sky culture, and
the IAU Catalog of Star Names, then pass those local inputs to this script.
The generator never downloads data. Input hashes are pinned below so a source
update has to be reviewed explicitly.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import astropy.units as u
from astropy.coordinates import FK4, FK5, SkyCoord
from astropy.time import Time


class SkyDataError(Exception):
    """Raised when source sky data cannot be converted safely."""


STAR_MAGNITUDE_LIMIT = 6.0
STAR_NAME_MAGNITUDE_LIMIT = 3.5
SNAP_DISTANCE_DEG = 0.01
SAMPLE_TOLERANCE_ARCSEC = 1.0
SIMPLIFY_TOLERANCE_ARCSEC = 2.0
BOUNDARY_MAX_ERROR_ARCSEC = 6.0

PINNED_INPUTS: dict[str, str] = {
    "hyg_v44.csv.gz": "00b349893b9a53106dd488d8371e8d2fa586043e500bb3cdb8bff3931682197d",
    "index.json": "1f2f5ffd6c9e25a7d0dcfdbf1f756e2db03dd3b8ed4ec016a2839b09f6b0fe1e",
    "IAU-CSN.txt": "84fac0c90f1b19abc491c2793469e0caa7b003ad1bc93a790ca41147010d0eb0",
    "constellations.lines.json": (
        "294f66bef5d5cf50b1e17f16d2efa1d97a15131612c68dd935adef6e7373e13c"
    ),
    "constellations.json": "11e14f1ee19b71bff5ca8af3f6e6a20596c4609dd86d43c9a796054fce88030c",
}

# d3-celestial's package metadata and licence. LICENSE is copied into the repository, so its bytes
# are pinned too; they aren't recorded in sky.json.
PINNED_PACKAGE_FILES: dict[str, str] = {
    "package.json": "7a38987d9413347841bd421138a1f696c21a0a735bfb2723ca494d2a43a5a1f3",
    "LICENSE": "95e8d6c281db702112e3f990c9c2958a4b412e2cfc09d419ec33f1227aa8dce4",
}

INPUT_ORIGINS = {
    "hyg_v44.csv.gz": "https://codeberg.org/astronexus/hyg (HYG v4.4)",
    "index.json": "https://github.com/Stellarium/stellarium (modern sky culture)",
    "IAU-CSN.txt": "https://www.pas.rochester.edu/~emamajek/WGSN/IAU-CSN.txt",
    "constellations.lines.json": "d3-celestial@0.7.35",
    "constellations.json": "d3-celestial@0.7.35",
}

SOURCES_MD = """# Sky data sources

`sky.json` is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
It is an adaptation of HYG and Stellarium data. To rebuild it, fetch the four
local inputs below, unpack d3-celestial, and run from `backend/`:

```sh
uv run python scripts/build_sky_data.py \\
  --package-dir /path/to/d3-celestial/package \\
  --hyg /path/to/hyg_v44.csv.gz \\
  --stellarium-modern /path/to/modern/index.json \\
  --star-names /path/to/IAU-CSN.txt
```

The script checks each input against the SHA-256 it pins:

- **d3-celestial 0.7.35:** `npm pack d3-celestial@0.7.35`, then unpack it.
- **HYG v4.4:** `hyg/CURRENT/hyg_v44.csv.gz` from
  <https://codeberg.org/astronexus/hyg>, commit
  `53e3df311869e813ace5f1ad2ec4ce909f13256c` (stored with Git LFS).
- **Stellarium:** `skycultures/modern/index.json` from
  <https://github.com/Stellarium/stellarium>, commit
  `daace2add6a1bf886e8ee1934f51e9c69f818d18`.
- **IAU Catalog of Star Names:**
  <https://www.pas.rochester.edu/~emamajek/WGSN/IAU-CSN.txt>, last updated
  2022-04-04.

## Credits and licences

- **Stars:** HYG v4.4 by David Nash ([astronexus.com](https://astronexus.com/),
  [source](https://codeberg.org/astronexus/hyg)), CC BY-SA 4.0. NightCrate
  rounds positions and magnitudes, limits the list to magnitude 6, merges
  duplicate rounded positions, and retains a fainter star only when an IAU
  figure requires it.
- **Boundaries:** Stellarium's modern sky culture by the Stellarium
  contributors, CC BY-SA 4.0. Its IAU boundaries are Patrick Barbier's
  `edges_18` in B1875 coordinates. NightCrate precesses them to J2000, then
  adaptively fills and simplifies the lines.
- **Star names:** the IAU Catalog of Star Names from the IAU Working Group on
  Star Names ([WGSN information](https://exopla.net/star-names/modern-iau-star-names/)).
  WGSN states that the names are in the public domain; the catalogue file
  states that IAU-produced products are released under Creative Commons
  Attribution. NightCrate matches the names by Hipparcos number.
- **Constellation figures and name positions:** d3-celestial 0.7.35,
  BSD-3-Clause, Copyright © 2015 Olaf Frohn. See
  `LICENSE-d3-celestial.txt`. The stick figures come from IAU constellation
  charts credited to “IAU and Sky & Telescope magazine (Roger Sinnott & Rick
  Fienberg)”, with patterns by Alan MacRobert, under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Olaf Frohn
  modified the lines; NightCrate converts and joins them to its star list.

Most star positions and magnitudes originate from ESA's Hipparcos mission.
Credit: ESA (ESA 1997, *The Hipparcos and Tycho Catalogues*, ESA SP-1200).
HYG takes a few double-star components from the Yale Bright Star and Gliese
catalogues instead.
"""


@dataclass(frozen=True)
class HygStar:
    ra: float
    dec: float
    mag: float
    hip: int | None


@dataclass(frozen=True)
class Edge:
    vertex1: str
    vertex2: str
    kind: str
    corner1: tuple[float, float]
    corner2: tuple[float, float]
    codes: tuple[str, str]


@dataclass(frozen=True)
class OrientedEdge:
    edge: Edge
    reversed: bool = False

    @property
    def start(self) -> str:
        return self.edge.vertex2 if self.reversed else self.edge.vertex1

    @property
    def end(self) -> str:
        return self.edge.vertex1 if self.reversed else self.edge.vertex2


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rounded(value: float, places: int) -> float:
    rounded = round(float(value), places)
    return 0.0 if rounded == 0 else rounded


def _position(coordinates: list[float], places: int) -> list[float]:
    ra = _rounded(coordinates[0] % 360, places)
    if ra >= 360:
        ra = 0.0
    return [ra, _rounded(coordinates[1], places)]


def _great_circle_distance_deg(left: tuple[float, float], right: tuple[float, float]) -> float:
    left_ra, left_dec = map(math.radians, left)
    right_ra, right_dec = map(math.radians, right)
    sin_dec = math.sin((right_dec - left_dec) / 2)
    sin_ra = math.sin((right_ra - left_ra) / 2)
    haversine = sin_dec**2 + math.cos(left_dec) * math.cos(right_dec) * sin_ra**2
    return math.degrees(2 * math.asin(math.sqrt(min(1.0, haversine))))


def _snap_vertex(code: str, coordinates: list[float], stars: list[list[float]]) -> int:
    vertex = (float(coordinates[0]) % 360, float(coordinates[1]))
    distances = [_great_circle_distance_deg(vertex, (ra, dec)) for ra, dec, _magnitude in stars]
    nearest_index = min(range(len(stars)), key=distances.__getitem__)
    if distances[nearest_index] > SNAP_DISTANCE_DEG:
        raise SkyDataError(
            f"Constellation {code} vertex ({vertex[0]}, {vertex[1]}) has no star "
            f"within {SNAP_DISTANCE_DEG}°"
        )
    return nearest_index


def read_hyg_stars(path: Path) -> list[HygStar]:
    """Read HYG's gzipped CSV and normalize the fields used by the chart."""
    rows: list[HygStar] = []
    with gzip.open(path, mode="rt", encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            if row["id"] == "0" or not row["mag"]:
                continue
            ra = _rounded((float(row["ra"]) * 15) % 360, 4)
            if ra >= 360:
                ra = 0.0
            rows.append(
                HygStar(
                    ra=ra,
                    dec=_rounded(float(row["dec"]), 4),
                    mag=_rounded(float(row["mag"]), 2),
                    hip=int(row["hip"]) if row["hip"] else None,
                )
            )
    return rows


def _hip_key(star: HygStar) -> float:
    return star.hip if star.hip is not None else math.inf


def select_stars(
    rows: Iterable[HygStar], figure_vertices: Iterable[list[float]]
) -> tuple[list[list[float]], list[int | None]]:
    """Apply the magnitude cut, merge duplicates, and retain required vertices."""
    all_rows = list(rows)
    selected: dict[tuple[float, float], HygStar] = {}
    for row in all_rows:
        if row.mag > STAR_MAGNITUDE_LIMIT:
            continue
        key = (row.ra, row.dec)
        current = selected.get(key)
        if current is None or (row.mag, _hip_key(row)) < (current.mag, _hip_key(current)):
            selected[key] = row

    for coordinates in figure_vertices:
        vertex = (float(coordinates[0]) % 360, float(coordinates[1]))
        if any(
            _great_circle_distance_deg(vertex, (row.ra, row.dec)) <= SNAP_DISTANCE_DEG
            for row in selected.values()
        ):
            continue
        candidates = [
            (
                round(_great_circle_distance_deg(vertex, (row.ra, row.dec)), 14),
                row.mag,
                _hip_key(row),
                row,
            )
            for row in all_rows
            if _great_circle_distance_deg(vertex, (row.ra, row.dec)) <= SNAP_DISTANCE_DEG
        ]
        if not candidates:
            raise SkyDataError(
                f"Figure vertex ({vertex[0]}, {vertex[1]}) has no HYG star within "
                f"{SNAP_DISTANCE_DEG}°"
            )
        nearest = min(candidates, key=lambda item: item[:3])[3]
        key = (nearest.ra, nearest.dec)
        current = selected.get(key)
        if current is None or (nearest.mag, _hip_key(nearest)) < (
            current.mag,
            _hip_key(current),
        ):
            selected[key] = nearest

    ordered = sorted(selected.values(), key=lambda star: (star.mag, star.ra, star.dec))
    return [[star.ra, star.dec, star.mag] for star in ordered], [star.hip for star in ordered]


_IAU_TAIL = re.compile(
    r"(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+"
    r"(\d{4}-\d{2}-\d{2})\s*\*?\s*$"
)


def parse_iau_star_names(text: str) -> dict[int, str]:
    """Map HIP numbers to the IAU catalogue's diacritics-preserving names."""
    names: dict[int, str] = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith(("#", "$")):
            continue
        match = _IAU_TAIL.search(line)
        if not match:
            raise SkyDataError(f"Malformed IAU star-name line {line_number}: {line!r}")
        if match.group(3) == "_":
            continue
        hip = int(match.group(3))
        if hip in names:
            raise SkyDataError(f"Repeated HIP {hip} in IAU star names")
        names[hip] = line[18:36].strip()
    if not names:
        raise SkyDataError("IAU star-name input contained no names with HIP numbers")
    return names


def _parse_ra(value: str) -> float:
    hours, minutes, seconds = (float(part) for part in value.split(":"))
    return (hours + minutes / 60 + seconds / 3600) * 15


def _parse_dec(value: str) -> float:
    sign = -1 if value.startswith("-") else 1
    degrees, minutes, seconds = (float(part) for part in value[1:].split(":"))
    return sign * (degrees + minutes / 60 + seconds / 3600)


def read_stellarium_edges(index_json: dict) -> list[Edge]:
    """Parse Stellarium's B1875 boundary-edge records."""
    if index_json.get("edges_epoch") != "B1875":
        raise SkyDataError(f"Unsupported boundary epoch: {index_json.get('edges_epoch')!r}")
    edges: list[Edge] = []
    for line in index_json.get("edges", []):
        fields = line.split()
        if len(fields) != 8 or ":" not in fields[0] or fields[1] not in {"M+", "P+"}:
            raise SkyDataError(f"Malformed Stellarium boundary edge: {line!r}")
        vertex1, vertex2 = fields[0].split(":", 1)
        try:
            corner1 = (_parse_ra(fields[2]), _parse_dec(fields[3]))
            corner2 = (_parse_ra(fields[4]), _parse_dec(fields[5]))
        except (TypeError, ValueError) as error:
            raise SkyDataError(f"Malformed Stellarium boundary edge: {line!r}") from error
        edges.append(
            Edge(
                vertex1=vertex1,
                vertex2=vertex2,
                kind=fields[1][0],
                corner1=corner1,
                corner2=corner2,
                codes=(fields[6], fields[7]),
            )
        )
    return edges


def build_rings(edges: Iterable[Edge], codes: Iterable[str]) -> dict[str, list[list[OrientedEdge]]]:
    """Chain each constellation's unoriented shared edges into closed loops."""
    code_list = list(codes)
    canonical = {code.upper(): code for code in code_list}
    canonical.update({"SER1": "Ser", "SER2": "Ser"})
    by_code: dict[str, list[Edge]] = defaultdict(list)
    for edge in edges:
        for source_code in edge.codes:
            code = canonical.get(source_code.upper())
            if code is None:
                raise SkyDataError(f"Unknown constellation code {source_code!r}")
            by_code[code].append(edge)

    result: dict[str, list[list[OrientedEdge]]] = {}
    for code in code_list:
        constellation_edges = by_code.get(code, [])
        incident: dict[str, list[int]] = defaultdict(list)
        for index, edge in enumerate(constellation_edges):
            incident[edge.vertex1].append(index)
            incident[edge.vertex2].append(index)
        invalid = {vertex: items for vertex, items in incident.items() if len(items) != 2}
        if invalid:
            vertex, items = next(iter(invalid.items()))
            raise SkyDataError(
                f"Constellation {code} vertex {vertex} has degree {len(items)}, expected 2"
            )

        unused = set(range(len(constellation_edges)))
        rings: list[list[OrientedEdge]] = []
        while unused:
            first_index = min(unused)
            first = constellation_edges[first_index]
            ring = [OrientedEdge(first)]
            unused.remove(first_index)
            start = first.vertex1
            current = first.vertex2
            while current != start:
                candidates = [index for index in incident[current] if index in unused]
                if len(candidates) != 1:
                    raise SkyDataError(f"Constellation {code} ring does not close at {current}")
                edge_index = candidates[0]
                edge = constellation_edges[edge_index]
                oriented = OrientedEdge(edge, reversed=edge.vertex2 == current)
                if oriented.start != current:
                    raise SkyDataError(f"Constellation {code} ring is disconnected at {current}")
                ring.append(oriented)
                unused.remove(edge_index)
                current = oriented.end
            rings.append(ring)
        result[code] = rings
    return result


def edge_at(edge: Edge, t: float) -> tuple[float, float]:
    """Return a B1875 point along an edge in the edge's own direction."""
    if not 0 <= t <= 1:
        raise ValueError("edge parameter must be between 0 and 1")
    (ra1, dec1), (ra2, dec2) = edge.corner1, edge.corner2
    if edge.kind == "M":
        return ra1 % 360, dec1 + (dec2 - dec1) * t
    if edge.kind == "P":
        delta_ra = (ra2 - ra1) % 360
        return (ra1 + delta_ra * t) % 360, dec1
    raise SkyDataError(f"Unsupported boundary edge kind {edge.kind!r}")


def precess_b1875_to_j2000(
    points: Iterable[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Precess FK4 B1875 coordinates to FK5 J2000, vectorized by astropy."""
    values = list(points)
    if not values:
        return []
    coordinates = SkyCoord(
        ra=[point[0] for point in values] * u.deg,
        dec=[point[1] for point in values] * u.deg,
        frame=FK4(equinox=Time("B1875")),
    ).transform_to(FK5(equinox=Time("J2000")))
    return list(zip(coordinates.ra.deg % 360, coordinates.dec.deg, strict=True))


def linear_fill(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    """Match geometry.ts densifyRing: linear Dec and shortest-path RA."""
    delta_ra = b[0] - a[0]
    if delta_ra > 180:
        delta_ra -= 360
    if delta_ra < -180:
        delta_ra += 360
    return (a[0] + delta_ra * t) % 360, a[1] + (b[1] - a[1]) * t


def _edge_length_deg(edge: Edge) -> float:
    if edge.kind == "M":
        return abs(edge.corner2[1] - edge.corner1[1])
    return (edge.corner2[0] - edge.corner1[0]) % 360


def edge_polyline(edge: Edge) -> list[tuple[float, float]]:
    """Build an adaptively sampled, simplified, rounded J2000 edge."""
    endpoints = precess_b1875_to_j2000([edge_at(edge, 0), edge_at(edge, 1)])
    samples: list[tuple[float, tuple[float, float]]] = [(0.0, endpoints[0])]
    edge_length = _edge_length_deg(edge)

    def sample(
        t0: float,
        point0: tuple[float, float],
        t1: float,
        point1: tuple[float, float],
    ) -> None:
        middle_t = (t0 + t1) / 2
        middle = precess_b1875_to_j2000([edge_at(edge, middle_t)])[0]
        estimate = linear_fill(point0, point1, 0.5)
        error = _great_circle_distance_deg(middle, estimate) * 3600
        if error > SAMPLE_TOLERANCE_ARCSEC and (t1 - t0) * edge_length > 0.005:
            sample(t0, point0, middle_t, middle)
            sample(middle_t, middle, t1, point1)
        else:
            samples.append((t1, point1))

    sample(0.0, endpoints[0], 1.0, endpoints[1])

    kept: set[int] = {0, len(samples) - 1}

    def simplify(start: int, end: int) -> None:
        if end <= start + 1:
            return
        start_t, start_point = samples[start]
        end_t, end_point = samples[end]
        errors = [
            (
                _great_circle_distance_deg(
                    point,
                    linear_fill(start_point, end_point, (sample_t - start_t) / (end_t - start_t)),
                )
                * 3600,
                index,
            )
            for index, (sample_t, point) in enumerate(samples[start + 1 : end], start + 1)
        ]
        maximum, index = max(errors, default=(0.0, start))
        if maximum > SIMPLIFY_TOLERANCE_ARCSEC:
            kept.add(index)
            simplify(start, index)
            simplify(index, end)

    simplify(0, len(samples) - 1)
    result: list[tuple[float, float]] = []
    for index in sorted(kept):
        ra, dec = samples[index][1]
        rounded_ra = _rounded(ra % 360, 3)
        result.append((0.0 if rounded_ra >= 360 else rounded_ra, _rounded(dec, 3)))
    return result


def _build_figures(source: dict, stars: list[list[float]]) -> dict[str, list[list[int]]]:
    figures: dict[str, list[list[int]]] = {}
    for feature in source["features"]:
        code = str(feature["id"])
        lines = figures.setdefault(code, [])
        for line in feature["geometry"]["coordinates"]:
            lines.append([_snap_vertex(code, vertex, stars) for vertex in line])
    return figures


def _build_labels(source: dict) -> dict[str, dict]:
    features = source["features"]
    code_counts = Counter(str(feature["id"]) for feature in features)
    labels: dict[str, dict] = {}
    for feature in features:
        code = str(feature["id"])
        properties = feature["properties"]
        label = labels.setdefault(code, {"rank": int(properties["rank"]), "points": []})
        point = {"at": _position(feature["geometry"]["coordinates"], 2)}
        if code_counts[code] > 1:
            point["name"] = properties["name"]
        label["points"].append(point)
    return labels


def _figure_vertices(source: dict) -> list[list[float]]:
    return [
        vertex
        for feature in source["features"]
        for line in feature["geometry"]["coordinates"]
        for vertex in line
    ]


def _validate_hashes(
    paths: dict[str, Path], allow_unpinned: bool, pinned: dict[str, str] | None = None
) -> dict[str, str]:
    pinned = PINNED_INPUTS if pinned is None else pinned
    hashes = {name: _sha256(path) for name, path in paths.items()}
    if not allow_unpinned:
        for name, actual in hashes.items():
            expected = pinned[name]
            if actual != expected:
                raise SkyDataError(
                    f"Unpinned {name}: SHA-256 is {actual}, expected {expected}; "
                    "use --allow-unpinned only for a reviewed source update"
                )
    return hashes


def build_sky_data(
    package_dir: Path,
    hyg_path: Path,
    stellarium_index_path: Path,
    star_names_path: Path,
    *,
    allow_unpinned: bool = False,
) -> dict:
    """Build deterministic sky data from the four local source inputs."""
    package_dir = Path(package_dir)
    paths = {
        "hyg_v44.csv.gz": Path(hyg_path),
        "index.json": Path(stellarium_index_path),
        "IAU-CSN.txt": Path(star_names_path),
        "constellations.lines.json": package_dir / "data" / "constellations.lines.json",
        "constellations.json": package_dir / "data" / "constellations.json",
    }
    hashes = _validate_hashes(paths, allow_unpinned)
    _validate_hashes(
        {name: package_dir / name for name in PINNED_PACKAGE_FILES},
        allow_unpinned,
        PINNED_PACKAGE_FILES,
    )
    package = _load_json(package_dir / "package.json")
    figures_source = _load_json(paths["constellations.lines.json"])
    labels_source = _load_json(paths["constellations.json"])
    stellarium = _load_json(paths["index.json"])

    stars, hips = select_stars(
        read_hyg_stars(paths["hyg_v44.csv.gz"]), _figure_vertices(figures_source)
    )
    edges = read_stellarium_edges(stellarium)
    codes = list(dict.fromkeys(str(feature["id"]) for feature in labels_source["features"]))
    rings = build_rings(edges, codes)
    polylines = {edge: edge_polyline(edge) for edge in edges}
    boundaries: dict[str, list[list[list[float]]]] = {}
    for code in codes:
        boundaries[code] = []
        for ring in rings[code]:
            points: list[tuple[float, float]] = []
            for oriented in ring:
                edge_points = polylines[oriented.edge]
                if oriented.reversed:
                    edge_points = list(reversed(edge_points))
                points.extend(edge_points if not points else edge_points[1:])
            if not points or points[-1] != points[0]:
                raise SkyDataError(f"Constellation {code} generated an open boundary ring")
            boundaries[code].append([[ra, dec] for ra, dec in points])

    iau_names = parse_iau_star_names(paths["IAU-CSN.txt"].read_text(encoding="utf-8"))
    names = [
        [index, iau_names[hip]]
        for index, (star, hip) in enumerate(zip(stars, hips, strict=True))
        if star[2] <= STAR_NAME_MAGNITUDE_LIMIT and hip in iau_names
    ]
    origins = {
        **INPUT_ORIGINS,
        "constellations.lines.json": f"d3-celestial@{package['version']}",
        "constellations.json": f"d3-celestial@{package['version']}",
    }
    return {
        "source": {
            "inputs": {name: {"sha256": hashes[name], "origin": origins[name]} for name in paths}
        },
        "stars": stars,
        "figures": _build_figures(figures_source, stars),
        "boundaries": boundaries,
        "labels": _build_labels(labels_source),
        "names": names,
    }


def write_sky_data(data: dict, licence: bytes, out_dir: Path) -> None:
    """Write generated data and its required source notices."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sky.json").write_bytes(json.dumps(data, separators=(",", ":")).encode())
    (out_dir / "LICENSE-d3-celestial.txt").write_bytes(licence)
    (out_dir / "SOURCES.md").write_text(SOURCES_MD, encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--hyg", required=True, type=Path)
    parser.add_argument("--stellarium-modern", required=True, type=Path)
    parser.add_argument("--star-names", required=True, type=Path)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "frontend" / "src" / "data" / "sky",
    )
    parser.add_argument("--allow-unpinned", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data = build_sky_data(
        args.package_dir,
        args.hyg,
        args.stellarium_modern,
        args.star_names,
        allow_unpinned=args.allow_unpinned,
    )
    write_sky_data(data, (args.package_dir / "LICENSE").read_bytes(), args.out_dir)
    print(
        f"Wrote {len(data['stars']):,} stars, {len(data['names']):,} names, and "
        f"{sum(len(rings) for rings in data['boundaries'].values()):,} boundary rings "
        f"to {args.out_dir / 'sky.json'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
