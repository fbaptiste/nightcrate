"""Catalog file hashing cache regressions."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

from nightcrate.catalog_loader import hash as hash_module
from nightcrate.catalog_loader.hash import file_sha256


def test_file_sha256_reuses_digest_without_reopening(tmp_path: Path, monkeypatch):
    path = tmp_path / "catalog.tsv"
    path.write_bytes(b"first contents")
    digest = file_sha256(path)
    original_open = Path.open

    def fail_for_cached_path(self, *args, **kwargs):
        if self == path.resolve():
            raise AssertionError("cached file was reopened")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_for_cached_path)

    assert file_sha256(path) == digest


def test_file_sha256_rehashes_same_size_with_restored_mtime(tmp_path: Path):
    path = tmp_path / "catalog.tsv"
    path.write_bytes(b"first")
    before = path.stat()
    first = file_sha256(path)

    path.write_bytes(b"other")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))

    assert file_sha256(path) != first


def test_file_sha256_stops_after_three_changes_without_caching(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "changing.dat"
    contents = b"changes while hashing"
    path.write_bytes(contents)
    resolved = path.resolve()
    actual_stat = resolved.stat()

    for key in list(hash_module._FILE_SHA256_CACHE):
        if key[0] == resolved:
            del hash_module._FILE_SHA256_CACHE[key]

    stat_calls = 0
    reads = 0
    original_stat = Path.stat
    original_open = Path.open

    def changing_stat(self: Path, *args, **kwargs):
        nonlocal stat_calls
        if self == resolved:
            stat_calls += 1
            return SimpleNamespace(
                st_size=actual_stat.st_size,
                st_mtime_ns=actual_stat.st_mtime_ns + stat_calls,
                st_ctime_ns=actual_stat.st_ctime_ns,
                st_ino=actual_stat.st_ino,
            )
        return original_stat(self, *args, **kwargs)

    def counting_open(self: Path, *args, **kwargs):
        nonlocal reads
        if self == resolved:
            reads += 1
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", changing_stat)
    monkeypatch.setattr(Path, "open", counting_open)

    assert file_sha256(path) == hashlib.sha256(contents).hexdigest()
    assert reads == 3
    assert not any(key[0] == resolved for key in hash_module._FILE_SHA256_CACHE)
