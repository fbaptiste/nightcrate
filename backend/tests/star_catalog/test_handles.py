from nightcrate.core import app_config
from nightcrate.services.star_catalog import handles

from .conftest import SyntheticStar, write_siril_catalog


def test_handles_close_all_closes_and_reopens(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "APP_DIR", tmp_path)
    from nightcrate.services.star_catalog.store import catalog_path

    write_siril_catalog(catalog_path(), [SyntheticStar(0, 0)])
    first = handles.get_catalog()
    handles.close_all()
    second = handles.get_catalog()
    assert first.closed
    assert second is not first
    handles.close_all()
