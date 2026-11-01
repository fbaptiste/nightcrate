import json

from nightcrate.core import app_config
from nightcrate.services.star_catalog import index, ranges
from nightcrate.services.star_catalog.store import SIRIL_SOURCE


def test_layer_state_stale_on_checksum_or_version(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    path = ranges.layer_path("q256")
    path.parent.mkdir(parents=True)
    metadata = {
        "format": index.INDEX_FORMAT,
        "version": index.INDEX_FORMAT_VERSION,
        "epoch": 2026.0,
        "source": {"uncompressed_sha256": SIRIL_SOURCE.uncompressed_sha256},
        "band": ranges.LAYERS["q256"].__dict__,
        "counts": {"tiles": 0, "stars": 0, "quads": 0},
        "layout": {
            "tile_offset": index.HEADER_SIZE,
            "star_offset": index.HEADER_SIZE,
            "quad_offset": index.HEADER_SIZE,
        },
    }
    encoded = json.dumps(metadata).encode()
    path.write_bytes(
        index.MAGIC
        + len(encoded).to_bytes(4, "little")
        + encoded
        + b"\0" * (index.HEADER_SIZE - 12 - len(encoded))
    )
    assert index.layer_state("q256") == "ready"
    metadata["source"]["uncompressed_sha256"] = "wrong"
    encoded = json.dumps(metadata).encode()
    path.write_bytes(
        index.MAGIC
        + len(encoded).to_bytes(4, "little")
        + encoded
        + b"\0" * (index.HEADER_SIZE - 12 - len(encoded))
    )
    assert index.layer_state("q256") == "stale"


def test_index_constants():
    assert index.INDEX_FORMAT == "nightcrate-star-index"
    assert index.INDEX_FORMAT_VERSION == 1
