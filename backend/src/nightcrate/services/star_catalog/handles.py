from __future__ import annotations

import threading
from collections.abc import Iterable
from typing import TYPE_CHECKING

from .siril import SirilCatalog
from .store import catalog_path

if TYPE_CHECKING:
    from .index import IndexLayer

_lock = threading.Lock()
_catalog: SirilCatalog | None = None
_layers: dict[str, IndexLayer] = {}


def get_catalog() -> SirilCatalog:
    global _catalog
    with _lock:
        if _catalog is None or _catalog.closed:
            _catalog = SirilCatalog(catalog_path())
        return _catalog


def get_layers(names: Iterable[str]) -> list[IndexLayer]:
    from .index import IndexLayer
    from .ranges import layer_path

    result: list[IndexLayer] = []
    with _lock:
        for name in names:
            layer = _layers.get(name)
            if layer is None or getattr(layer, "closed", False):
                layer = IndexLayer(layer_path(name))
                _layers[name] = layer
            result.append(layer)
    return result


def close_all() -> None:
    global _catalog
    with _lock:
        if _catalog is not None:
            _catalog.close()
        _catalog = None
        for layer in _layers.values():
            layer.close()
        _layers.clear()
