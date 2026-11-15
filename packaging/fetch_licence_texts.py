"""Fetch the pinned SPDX canonical licence texts used by release notices."""

from __future__ import annotations

import argparse
import re
import shutil
import ssl
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import certifi

SPDX_TAG = "v3.27.0"
SPDX_RAW_BASE = (
    f"https://raw.githubusercontent.com/spdx/license-list-data/{SPDX_TAG}/text"
)
POLICY_PATH = Path(__file__).with_name("licence_policy.toml")
DEFAULT_OUT = Path(__file__).with_name("licence-texts")
SPDX_TOKEN = re.compile(
    r"\(|\)|\bAND\b|\bOR\b|\bWITH\b|[A-Za-z0-9][A-Za-z0-9.+-]*",
    re.IGNORECASE,
)


def _identifiers(expression: str) -> set[str]:
    tokens = SPDX_TOKEN.findall(expression)
    compact_input = re.sub(r"\s+", "", expression)
    if compact_input.lower() != "".join(tokens).lower():
        raise ValueError(f"cannot parse licence expression {expression!r}")
    return {
        token
        for token in tokens
        if token.upper() not in {"AND", "OR", "WITH"} and token not in {"(", ")"}
    }


def _policy_identifiers(policy: dict[str, Any]) -> list[str]:
    expressions = list(policy.get("accepted", []))
    expressions.extend(policy.get("scoped", {}).keys())
    expressions.extend(policy.get("choices", {}).values())
    return sorted(
        identifier
        for expression in expressions
        for identifier in _identifiers(expression)
    )


def fetch(destination: Path) -> None:
    with POLICY_PATH.open("rb") as handle:
        identifiers = sorted(set(_policy_identifiers(tomllib.load(handle))))
    context = ssl.create_default_context(cafile=certifi.where())
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="nightcrate-spdx-", dir=destination.parent
    ) as temporary_name:
        temporary = Path(temporary_name)
        for identifier in identifiers:
            filename = f"{identifier}.txt"
            # SPDX keeps deprecated identifiers (e.g. GPL-3.0) as
            # text/deprecated_<id>.txt; try the current name first.
            errors = []
            for published in (filename, f"deprecated_{filename}"):
                url = f"{SPDX_RAW_BASE}/{urllib.parse.quote(published, safe='')}"
                request = urllib.request.Request(
                    url, headers={"User-Agent": "NightCrate-release-builder"}
                )
                try:
                    with urllib.request.urlopen(  # noqa: S310
                        request, timeout=60, context=context
                    ) as response:
                        with (temporary / filename).open("wb") as output:
                            shutil.copyfileobj(response, output)
                    break
                except (OSError, urllib.error.URLError) as exc:
                    errors.append(f"{url}: {exc}")
            else:
                raise RuntimeError(f"failed to fetch {identifier}: {'; '.join(errors)}")
        for path in sorted(temporary.iterdir()):
            path.replace(destination / path.name)
    print(f"fetched {len(identifiers)} SPDX texts from {SPDX_TAG} into {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    fetch(args.out)


if __name__ == "__main__":
    main()
