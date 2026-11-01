import json
from dataclasses import replace

from nightcrate.core import app_config
from nightcrate.services.star_catalog import store


def test_star_root_follows_app_dir_redirect(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    assert store.star_root() == tmp_path / "star_catalogs"


def test_installed_requires_version_json_and_size(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    monkeypatch.setattr(store, "SIRIL_SOURCE", replace(store.SIRIL_SOURCE, uncompressed_size=3))
    store.catalog_dir().mkdir(parents=True)
    store.catalog_path().write_bytes(b"abc")
    assert store.installed() is None
    payload = store.version_payload("import")
    (store.catalog_dir() / "version.json").write_text(json.dumps(payload))
    assert store.installed() is not None


def test_required_free_bytes_accounts_for_partial(monkeypatch):
    monkeypatch.setattr(
        store,
        "SIRIL_SOURCE",
        replace(store.SIRIL_SOURCE, compressed_size=100, uncompressed_size=200),
    )
    assert store.required_free_bytes(40) == 60 + 200 + 100 * 1024 * 1024
