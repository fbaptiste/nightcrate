"""Tests for the deterministic licensed sky-data generator."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

import scripts.build_sky_data as build_module
from scripts.build_sky_data import (
    BOUNDARY_MAX_ERROR_ARCSEC,
    PINNED_INPUTS,
    PINNED_PACKAGE_FILES,
    SOURCES_MD,
    Edge,
    HygStar,
    SkyDataError,
    build_rings,
    build_sky_data,
    edge_at,
    edge_polyline,
    linear_fill,
    parse_iau_star_names,
    precess_b1875_to_j2000,
    read_hyg_stars,
    read_stellarium_edges,
    select_stars,
    write_sky_data,
)

ROOT = Path(__file__).resolve().parents[2]
SKY_DIR = ROOT / "frontend" / "src" / "data" / "sky"


def _distance_arcsec(left: tuple[float, float], right: tuple[float, float]) -> float:
    left_ra, left_dec = map(math.radians, left)
    right_ra, right_dec = map(math.radians, right)
    haversine = (
        math.sin((right_dec - left_dec) / 2) ** 2
        + math.cos(left_dec) * math.cos(right_dec) * math.sin((right_ra - left_ra) / 2) ** 2
    )
    return math.degrees(2 * math.asin(math.sqrt(min(1.0, haversine)))) * 3600


def _distance_to_polyline(point: tuple[float, float], line: list[tuple[float, float]]) -> float:
    best = min(_distance_arcsec(point, vertex) for vertex in line)
    for start, end in zip(line, line[1:], strict=False):
        low = 0.0
        high = 1.0
        for _pass in range(24):
            left = low + (high - low) / 3
            right = high - (high - low) / 3
            if _distance_arcsec(point, linear_fill(start, end, left)) < _distance_arcsec(
                point, linear_fill(start, end, right)
            ):
                high = right
            else:
                low = left
        best = min(best, _distance_arcsec(point, linear_fill(start, end, (low + high) / 2)))
    return best


def _edge(
    vertex1: str,
    vertex2: str,
    corner1: tuple[float, float],
    corner2: tuple[float, float],
    codes: tuple[str, str] = ("SYN", "OUT"),
    kind: str = "M",
) -> Edge:
    return Edge(vertex1, vertex2, kind, corner1, corner2, codes)


def _square(
    prefix: str = "",
    codes: tuple[str, str] = ("SYN", "OUT"),
) -> list[Edge]:
    return [
        _edge(f"{prefix}1", f"{prefix}2", (10, 0), (10, 1), codes),
        _edge(f"{prefix}3", f"{prefix}2", (11, 1), (10, 1), codes, "P"),
        _edge(f"{prefix}3", f"{prefix}4", (11, 1), (11, 0), codes),
        _edge(f"{prefix}1", f"{prefix}4", (10, 0), (11, 0), codes, "P"),
    ]


def _iau_line(name: str, diacritics: str, hip: int | str, date: str = "2020-01-01") -> str:
    return f"{name:<18}{diacritics:<18}HR 1 alf α Syn _ _ 1.0 V {hip} 456 1 2 {date}"


def _write_hyg(path: Path, rows: list[dict[str, str]]) -> None:
    fields = ["id", "hip", "ra", "dec", "mag"]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_read_hyg_stars_skips_sun_and_empty_magnitude_and_wraps_ra(tmp_path: Path):
    path = tmp_path / "hyg.csv.gz"
    _write_hyg(
        path,
        [
            {"id": "0", "hip": "", "ra": "0", "dec": "0", "mag": "-26.7"},
            {"id": "1", "hip": "1", "ra": "23.99999", "dec": "1.23456", "mag": "2.345"},
            {"id": "2", "hip": "2", "ra": "23.999999", "dec": "-2", "mag": "3"},
            {"id": "3", "hip": "", "ra": "1", "dec": "3", "mag": ""},
        ],
    )

    assert read_hyg_stars(path) == [
        HygStar(359.9998, 1.2346, 2.35, 1),
        HygStar(0.0, -2.0, 3.0, 2),
    ]


def test_select_stars_cuts_merges_ties_and_keeps_required_faint_star():
    rows = [
        HygStar(10, 1, 6.01, 1),
        HygStar(20, 2, 3, 30),
        HygStar(20, 2, 2, 31),
        HygStar(30, 3, 2, 40),
        HygStar(30, 3, 2, 39),
        HygStar(40, 4, 7, 50),
    ]

    stars, hips = select_stars(rows, [[20.0001, 2], [40.0001, 4]])

    assert stars == [[20, 2, 2], [30, 3, 2], [40, 4, 7]]
    assert hips == [31, 39, 50]


def test_select_stars_does_not_readd_merged_duplicate_for_nearby_vertex():
    rows = [HygStar(10, 0, 2, 2), HygStar(10, 0, 3, 1)]

    stars, hips = select_stars(rows, [[10.001, 0]])

    assert stars == [[10, 0, 2]]
    assert hips == [2]


def test_build_rings_orients_square_and_wrap_edge_both_ways():
    edges = _square()
    edges[3] = _edge("1", "4", (359, 0), (1, 0), kind="P")

    rings = build_rings(edges, ["Syn", "Out"])

    assert len(rings["Syn"]) == 1
    assert [item.start for item in rings["Syn"][0]] == ["1", "2", "3", "4"]
    assert [item.end for item in rings["Syn"][0]] == ["2", "3", "4", "1"]
    assert any(item.reversed for item in rings["Syn"][0])
    syn_wrap = next(
        item for item in rings["Syn"][0] if item.edge.kind == "P" and item.edge is edges[3]
    )
    out_wrap = next(
        item for item in rings["Out"][0] if item.edge.kind == "P" and item.edge is edges[3]
    )
    assert syn_wrap.reversed
    assert out_wrap.reversed


def test_build_rings_keeps_two_serpens_loops():
    edges = [
        *_square("a", ("SER1", "OUT")),
        *_square("b", ("SER2", "OUT")),
    ]

    rings = build_rings(edges, ["Ser", "Out"])

    assert len(rings["Ser"]) == 2
    assert len(rings["Out"]) == 2


@pytest.mark.parametrize(
    ("edges", "codes", "message"),
    [
        (_square()[:-1], ["Syn", "Out"], "degree 1"),
        (
            [*_square(), _edge("1", "3", (10, 0), (11, 1), kind="P")],
            ["Syn", "Out"],
            "degree 3",
        ),
        (_square(codes=("BAD", "OUT")), ["Syn", "Out"], "Unknown constellation"),
    ],
)
def test_build_rings_rejects_invalid_topology(edges: list[Edge], codes: list[str], message: str):
    with pytest.raises(SkyDataError, match=message):
        build_rings(edges, codes)


def test_edge_at_handles_meridian_and_parallel_wrap():
    meridian = _edge("1", "2", (120, -10), (120, 20))
    parallel = _edge("1", "2", (359, 10), (1, 10), kind="P")

    assert edge_at(meridian, 0.25) == (120, -2.5)
    assert edge_at(parallel, 0.75) == (0.5, 10)


def test_precession_matches_previous_vi49_corner_before_rounding():
    actual = precess_b1875_to_j2000([(343.0, 34.5)])[0]

    assert _distance_arcsec(actual, (344.465, 35.168)) < 4


def test_edge_polyline_meets_dense_reference_budget_near_north_pole():
    edge = _edge("1", "2", (120, 86.5), (120, 88.0))
    line = edge_polyline(edge)
    b1875 = [(120, 86.5 + index * 0.01) for index in range(151)]
    reference = precess_b1875_to_j2000(b1875)

    forward = max(_distance_to_polyline(point, line) for point in reference)
    reverse = max(_distance_to_polyline(point, reference) for point in line)
    assert forward <= BOUNDARY_MAX_ERROR_ARCSEC
    assert reverse <= BOUNDARY_MAX_ERROR_ARCSEC


def test_parse_iau_star_names_uses_diacritics_and_skips_missing_hip():
    text = "\n".join(
        [
            "# comment",
            "$ source",
            _iau_line("Ascii", "Bélénos", 123),
            _iau_line("No HIP", "No HIP", "_"),
        ]
    )

    assert parse_iau_star_names(text) == {123: "Bélénos"}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not a catalogue row", "Malformed"),
        ("\n".join([_iau_line("One", "One", 1), _iau_line("Two", "Two", 1)]), "Repeated"),
        (_iau_line("No HIP", "No HIP", "_"), "no names"),
    ],
)
def test_parse_iau_star_names_rejects_bad_data(text: str, message: str):
    with pytest.raises(SkyDataError, match=message):
        parse_iau_star_names(text)


def test_read_stellarium_edges_rejects_epoch_kind_and_malformed_lines():
    with pytest.raises(SkyDataError, match="epoch"):
        read_stellarium_edges({"edges_epoch": "J2000", "edges": []})
    with pytest.raises(SkyDataError, match="Malformed"):
        read_stellarium_edges({"edges_epoch": "B1875", "edges": ["1:2 X+ 0 0 0 0 A B"]})
    with pytest.raises(SkyDataError, match="Malformed"):
        read_stellarium_edges({"edges_epoch": "B1875", "edges": ["broken"]})


def _synthetic_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    package = tmp_path / "package"
    data_dir = package / "data"
    data_dir.mkdir(parents=True)
    (package / "LICENSE").write_bytes(b"synthetic licence\n")
    (package / "package.json").write_text('{"version":"0.0.0"}', encoding="utf-8")

    def collection(features: list[dict]) -> dict:
        return {"type": "FeatureCollection", "features": features}

    def point(code: str, coordinates: list[float], properties: dict) -> dict:
        return {
            "type": "Feature",
            "id": code,
            "properties": properties,
            "geometry": {"type": "Point", "coordinates": coordinates},
        }

    figures = [
        {
            "type": "Feature",
            "id": "Syn",
            "properties": {},
            "geometry": {"type": "MultiLineString", "coordinates": [[[15, 0], [30, 0]]]},
        }
    ]
    labels = [
        point("Syn", [15, 0], {"rank": "1", "name": "Synthetic"}),
        point("Out", [30, 0], {"rank": "2", "name": "Outside"}),
    ]
    (data_dir / "constellations.lines.json").write_text(json.dumps(collection(figures)))
    (data_dir / "constellations.json").write_text(json.dumps(collection(labels)))
    hyg = tmp_path / "hyg_v44.csv.gz"
    _write_hyg(
        hyg,
        [
            {"id": "1", "hip": "123", "ra": "1", "dec": "0", "mag": "1"},
            {"id": "2", "hip": "456", "ra": "2", "dec": "0", "mag": "2"},
        ],
    )
    stellarium = tmp_path / "index.json"
    stellarium.write_text(
        json.dumps(
            {
                "edges_epoch": "B1875",
                "edges": [
                    "1:2 M+ 01:00:00 +00:00:00 01:00:00 +01:00:00 SYN OUT",
                    "3:2 P+ 02:00:00 +01:00:00 01:00:00 +01:00:00 SYN OUT",
                    "3:4 M+ 02:00:00 +01:00:00 02:00:00 +00:00:00 SYN OUT",
                    "1:4 P+ 01:00:00 +00:00:00 02:00:00 +00:00:00 SYN OUT",
                ],
            }
        )
    )
    names = tmp_path / "IAU-CSN.txt"
    names.write_text(_iau_line("Ascii", "Bélénos", 123), encoding="utf-8")
    return package, hyg, stellarium, names


def test_build_sky_data_and_pinning(tmp_path: Path):
    package, hyg, stellarium, names = _synthetic_inputs(tmp_path)

    with pytest.raises(SkyDataError, match="Unpinned"):
        build_sky_data(package, hyg, stellarium, names)
    result = build_sky_data(package, hyg, stellarium, names, allow_unpinned=True)

    assert list(result) == ["source", "stars", "figures", "boundaries", "labels", "names"]
    assert result["stars"] == [[15.0, 0.0, 1.0], [30.0, 0.0, 2.0]]
    assert result["figures"] == {"Syn": [[0, 1]]}
    assert result["names"] == [[0, "Bélénos"]]
    assert set(result["source"]["inputs"]) == set(PINNED_INPUTS)
    assert all(ring[0] == ring[-1] for rings in result["boundaries"].values() for ring in rings)


def test_package_metadata_and_licence_are_pinned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    package, hyg, stellarium, names = _synthetic_inputs(tmp_path)
    data_paths = {
        "hyg_v44.csv.gz": hyg,
        "index.json": stellarium,
        "IAU-CSN.txt": names,
        "constellations.lines.json": package / "data" / "constellations.lines.json",
        "constellations.json": package / "data" / "constellations.json",
    }
    monkeypatch.setattr(
        build_module,
        "PINNED_INPUTS",
        {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in data_paths.items()},
    )

    # Data files match their pins, but the package's metadata doesn't.
    with pytest.raises(SkyDataError, match="Unpinned package.json"):
        build_sky_data(package, hyg, stellarium, names)

    monkeypatch.setattr(
        build_module,
        "PINNED_PACKAGE_FILES",
        {
            "package.json": hashlib.sha256((package / "package.json").read_bytes()).hexdigest(),
            "LICENSE": PINNED_PACKAGE_FILES["LICENSE"],
        },
    )
    # A licence that isn't d3-celestial's own is rejected before it can be copied.
    with pytest.raises(SkyDataError, match="Unpinned LICENSE"):
        build_sky_data(package, hyg, stellarium, names)

    assert build_sky_data(package, hyg, stellarium, names, allow_unpinned=True)["names"]


def test_write_copies_licence_and_sources(tmp_path: Path):
    data = {
        "source": {},
        "stars": [],
        "figures": {},
        "boundaries": {},
        "labels": {},
        "names": [],
    }
    licence = b"BSD licence bytes\x00\n"

    write_sky_data(data, licence, tmp_path)

    assert (tmp_path / "LICENSE-d3-celestial.txt").read_bytes() == licence
    assert (tmp_path / "SOURCES.md").read_text() == SOURCES_MD
    assert "https://creativecommons.org/licenses/by-sa/4.0/" in SOURCES_MD
    assert "Credit: ESA" in SOURCES_MD
    assert "VizieR" not in SOURCES_MD
    assert json.loads((tmp_path / "sky.json").read_bytes()) == data
    assert b" " not in (tmp_path / "sky.json").read_bytes()


def _named_positions(data: dict) -> dict[str, list[float]]:
    return {name: data["stars"][index][:2] for index, name in data["names"]}


def _ra_winding(ring: list[list[float]]) -> float:
    return sum(((right[0] - left[0] + 540) % 360) - 180 for left, right in zip(ring, ring[1:]))


def test_committed_sky_json_counts_names_topology_and_hashes():
    sky_path = SKY_DIR / "sky.json"
    data = json.loads(sky_path.read_bytes())

    assert list(data) == ["source", "stars", "figures", "boundaries", "labels", "names"]
    hashes = {name: item["sha256"] for name, item in data["source"]["inputs"].items()}
    assert hashes == PINNED_INPUTS
    assert len(data["stars"]) == 5_069
    assert sum(star[2] <= 6 for star in data["stars"]) == 5_068
    assert len(data["names"]) == 186
    assert sum(data["stars"][index][2] <= 1.5 for index, _name in data["names"]) == 23
    assert data["names"][0] == [0, "Sirius"]
    assert all(left[0] < right[0] for left, right in zip(data["names"], data["names"][1:]))
    assert all(
        index < len(data["stars"]) and data["stars"][index][2] <= 3.5 for index, _ in data["names"]
    )

    positions = _named_positions(data)
    for name, expected in {
        "Sirius": (101.2872, -16.7161),
        "Vega": (279.2346, 38.7837),
        "Dubhe": (165.9323, 61.7510),
        "Polaris": (37.9463, 89.2641),
    }.items():
        assert _distance_arcsec(tuple(positions[name]), expected) <= 3.6
    assert {"Dubhe", "Merak", "Phecda", "Megrez", "Alioth", "Mizar", "Alkaid"} <= positions.keys()
    assert "Schedar" in positions
    assert {"Regor", "Navi", "Shedar"}.isdisjoint(positions)

    assert len(data["boundaries"]) == 88
    assert len(data["boundaries"]["Ser"]) == 2
    assert sum(map(len, data["boundaries"].values())) == 89
    assert all(ring[0] == ring[-1] for rings in data["boundaries"].values() for ring in rings)
    for code, rings in data["boundaries"].items():
        winding = sum(_ra_winding(ring) for ring in rings)
        if code in {"Oct", "UMi"}:
            assert abs(abs(winding) - 360) < 1e-6
        else:
            assert abs(winding) < 1e-6, code

    assert all(
        index < len(data["stars"])
        for lines in data["figures"].values()
        for line in lines
        for index in line
    )
    assert sky_path.stat().st_size < 250_000
    licence = (SKY_DIR / "LICENSE-d3-celestial.txt").read_bytes()
    assert b"Copyright (c) 2015, Olaf Frohn" in licence
    assert hashlib.sha256(licence).hexdigest() == PINNED_PACKAGE_FILES["LICENSE"]
