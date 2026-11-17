"""Pure helpers for stable CI test sharding."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Shard:
    index: int
    total: int


@dataclass(frozen=True)
class ShardItem:
    key: str
    pin_to_first: bool = False


def parse_shard(value: str) -> Shard:
    """Parse the one-based ``i/n`` shard syntax used by CI."""
    match = re.fullmatch(r"([1-9]\d*)/([1-9]\d*)", value)
    if match is None:
        raise ValueError("expected i/n with positive integers, for example 2/6")
    index, total = (int(part) for part in match.groups())
    if index > total:
        raise ValueError(f"shard index {index} exceeds shard count {total}")
    return Shard(index=index, total=total)


def shard_index(key: str, total: int) -> int:
    """Return the zero-based stable shard index for a node or group key."""
    if total < 1:
        raise ValueError("shard count must be positive")
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest, "big") % total


def select_shard(items: list[ShardItem], shard: Shard) -> list[bool]:
    """Return a mask, pinning marked keys first and keeping groups together."""
    pinned_keys = {item.key for item in items if item.pin_to_first}
    return [
        shard.index == 1
        if item.key in pinned_keys
        else shard_index(item.key, shard.total) == shard.index - 1
        for item in items
    ]
