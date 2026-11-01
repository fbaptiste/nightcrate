from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from nightcrate.core import app_config

_MIB = 1024 * 1024


@dataclass(frozen=True)
class SirilSource:
    record_id: int = 14692304
    version: str = "1.0.0"
    doi: str = "10.5281/zenodo.14692304"
    format_doi: str = "10.5281/zenodo.14697486"
    url: str = (
        "https://zenodo.org/records/14692304/files/siril_cat_healpix8_astro.dat.bz2?download=1"
    )
    compressed_name: str = "siril_cat_healpix8_astro.dat.bz2"
    compressed_size: int = 1_142_276_749
    compressed_sha256: str = "846ad4b12c50865df0cb8c5b23453f22eec78bbe9969e17d669ae19eb49d421f"
    uncompressed_name: str = "siril_cat_healpix8_astro.dat"
    uncompressed_size: int = 1_521_132_640
    uncompressed_sha256: str = "2fa40c93fe115235d35c5050757f2ef60a326a6f3030f87be1598c016fcb2388"
    licence: str = "CC BY 4.0"
    gaia_licence: str = "CC BY-NC 3.0 IGO"
    attribution: str = (
        "Siril Astrometry Catalogue by the Siril team. This work has made use of "
        "data from the European Space Agency (ESA) mission Gaia "
        "(https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing "
        "and Analysis Consortium (DPAC, "
        "https://www.cosmos.esa.int/web/gaia/dpac/consortium). Funding for the DPAC "
        "has been provided by national institutions, in particular the institutions "
        "participating in the Gaia Multilateral Agreement."
    )


SIRIL_SOURCE = SirilSource()


@dataclass(frozen=True)
class InstalledCatalog:
    version: str
    size_bytes: int
    installed_at: str
    source: Literal["download", "import"]
    uncompressed_sha256: str


class AlreadyInstalled(ValueError):
    pass


class InsufficientSpace(ValueError):
    def __init__(self, needed: int, free: int):
        self.needed = needed
        self.free = free
        super().__init__(f"Need {needed} bytes free; only {free} bytes are available.")


def star_root() -> Path:
    return app_config.APP_DIR / "star_catalogs"


def catalog_dir() -> Path:
    return star_root() / f"siril-astro-gaia-dr3-{SIRIL_SOURCE.version}"


def catalog_path() -> Path:
    return catalog_dir() / SIRIL_SOURCE.uncompressed_name


def staging_dir() -> Path:
    return star_root() / ".staging"


def installed() -> InstalledCatalog | None:
    version_file = catalog_dir() / "version.json"
    try:
        data = json.loads(version_file.read_text(encoding="utf-8"))
        path = catalog_path()
        if path.stat().st_size != SIRIL_SOURCE.uncompressed_size:
            return None
        if data["source"] not in {"download", "import"}:
            return None
        result = InstalledCatalog(
            version=data["version"],
            size_bytes=path.stat().st_size,
            installed_at=data["installed_at"],
            source=data["source"],
            uncompressed_sha256=data["uncompressed_sha256"],
        )
        if (
            result.version != SIRIL_SOURCE.version
            or result.uncompressed_sha256 != SIRIL_SOURCE.uncompressed_sha256
        ):
            return None
        return result
    except OSError, KeyError, TypeError, ValueError, json.JSONDecodeError:
        return None


def required_free_bytes(already_downloaded: int) -> int:
    return (
        max(0, SIRIL_SOURCE.compressed_size - already_downloaded)
        + SIRIL_SOURCE.uncompressed_size
        + 100 * _MIB
    )


def ensure_free_space(already_downloaded: int = 0) -> None:
    root = star_root()
    root.mkdir(parents=True, exist_ok=True)
    needed = required_free_bytes(already_downloaded)
    free = shutil.disk_usage(root).free
    if free < needed:
        raise InsufficientSpace(needed, free)


def version_payload(source: Literal["download", "import"]) -> dict[str, object]:
    return {
        "record_id": SIRIL_SOURCE.record_id,
        "version": SIRIL_SOURCE.version,
        "doi": SIRIL_SOURCE.doi,
        "format_doi": SIRIL_SOURCE.format_doi,
        "file_name": SIRIL_SOURCE.uncompressed_name,
        "compressed_sha256": SIRIL_SOURCE.compressed_sha256,
        "uncompressed_sha256": SIRIL_SOURCE.uncompressed_sha256,
        "installed_at": datetime.now(UTC).isoformat(),
        "source": source,
        "licence": SIRIL_SOURCE.licence,
        "gaia_licence": SIRIL_SOURCE.gaia_licence,
        "attribution": SIRIL_SOURCE.attribution,
    }
