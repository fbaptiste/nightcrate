from nightcrate.core import app_config
from nightcrate.services.star_catalog import ranges
from scripts import plate_solve_benchmark


def test_field_range_table():
    assert [
        (
            item.id,
            item.name,
            item.recommended,
            item.min_deg,
            item.max_deg,
            item.layers,
            item.estimated_bytes,
            item.build_memory_bytes,
        )
        for item in ranges.FIELD_RANGES
    ] == [
        (
            "0.4-10",
            "Standard",
            True,
            0.4,
            10.0,
            ("q008", "q016", "q032", "q064", "q128", "q256"),
            529_127_680,
            3_200_000_000,
        ),
        (
            "0.2-0.4",
            "Narrow fields",
            False,
            0.2,
            0.4,
            ("q004",),
            1_387_419_120,
            5_400_000_000,
        ),
    ]


def test_range_for_field_boundaries():
    expected = [
        (0.19, None),
        (0.2, "0.2-0.4"),
        (0.3999, "0.2-0.4"),
        (0.4, "0.4-10"),
        (10.0, "0.4-10"),
        (10.01, None),
    ]
    for value, range_id in expected:
        found = ranges.range_for_field(value)
        assert (found.id if found else None) == range_id


def test_manifest_atomic_and_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    ranges.write_manifest({"0.4-10", "0.4-0.8"})
    assert ranges.read_manifest() == {"0.4-10"}
    assert not ranges.manifest_path().with_suffix(".tmp").exists()


def test_benchmark_range_choices_match_product_ranges():
    assert tuple(plate_solve_benchmark.RANGE_LAYERS) == tuple(
        item.id for item in ranges.FIELD_RANGES
    )


def test_layer_specs_match_prototype():
    assert ranges.LAYERS["q004"].healpix_level == 10
    assert ranges.LAYERS["q256"].magnitude_limit == 8.0
    assert all(spec.stars_per_cell == 5 for spec in ranges.LAYERS.values())
    assert ranges.LAYERS["q128"].estimated_bytes == 2_358_712
    assert ranges.LAYERS["q256"].estimated_bytes == 780_872
    assert all(
        item.estimated_bytes == sum(ranges.LAYERS[name].estimated_bytes for name in item.layers)
        for item in ranges.FIELD_RANGES
    )
