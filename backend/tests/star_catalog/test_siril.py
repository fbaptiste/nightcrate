import bz2
import hashlib
import os

import pytest

from nightcrate.services.star_catalog.siril import (
    ChecksumMismatch,
    SirilCatalog,
    SirilFormatError,
    decompress_and_verify,
)

from .conftest import SyntheticStar, write_siril_catalog


def test_header_rejects_bad_magic(tmp_path):
    path = write_siril_catalog(tmp_path / "stars.dat", [])
    data = bytearray(path.read_bytes())
    data[0] = 0
    path.write_bytes(data)
    with pytest.raises(SirilFormatError):
        SirilCatalog(path)


def test_header_rejects_truncated_file(tmp_path):
    path = tmp_path / "stars.dat"
    path.write_bytes(b"short")
    with pytest.raises(SirilFormatError):
        SirilCatalog(path)


def test_cone_returns_only_stars_inside(tmp_path):
    path = write_siril_catalog(
        tmp_path / "stars.dat",
        [SyntheticStar(180 + offset, 0) for offset in (0.5, 0.9, 1.1, 2, 10)],
    )
    with SirilCatalog(path) as catalog:
        result = catalog.query_cone(180, 0, 1.0, epoch=2016.0)
    assert len(result) == 2
    assert sorted(result.ra.tolist()) == pytest.approx([180.5, 180.9], abs=1e-6)


def test_cone_spans_cell_boundaries(tmp_path):
    path = write_siril_catalog(
        tmp_path / "stars.dat",
        [SyntheticStar(179.99, 0), SyntheticStar(180.01, 0)],
    )
    with SirilCatalog(path) as catalog:
        assert len(catalog.query_cone(180, 0, 0.05)) == 2


def test_epoch_propagation(tmp_path):
    path = write_siril_catalog(tmp_path / "stars.dat", [SyntheticStar(0, 0, pmra=1000)])
    with SirilCatalog(path) as catalog:
        result = catalog.query_cone(0, 0, 1)
    assert result.ra[0] == pytest.approx(10 / 3600, abs=1e-8)


def test_decompress_and_verify_ok(tmp_path):
    raw = b"catalog bytes" * 100
    compressed = tmp_path / "catalog.bz2"
    compressed.write_bytes(bz2.compress(raw))
    output = tmp_path / "catalog.dat"
    result = decompress_and_verify(
        compressed,
        output,
        compressed_sha256=hashlib.sha256(compressed.read_bytes()).hexdigest(),
        uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
    )
    assert result.read_bytes() == raw


def test_decompress_and_verify_mismatch_leaves_no_output(tmp_path):
    compressed = tmp_path / "catalog.bz2"
    compressed.write_bytes(bz2.compress(b"bad"))
    original = compressed.read_bytes()
    output = tmp_path / "catalog.dat"
    with pytest.raises(ChecksumMismatch):
        decompress_and_verify(
            compressed,
            output,
            compressed_sha256=hashlib.sha256(original).hexdigest(),
            uncompressed_sha256="0" * 64,
        )
    assert not output.exists()
    assert compressed.read_bytes() == original


def test_close_releases_mapping(tmp_path):
    path = write_siril_catalog(tmp_path / "stars.dat", [SyntheticStar(0, 0)])
    catalog = SirilCatalog(path)
    catalog.close()
    replacement = write_siril_catalog(tmp_path / "replacement.dat", [])
    os.replace(replacement, path)
    assert catalog.closed
