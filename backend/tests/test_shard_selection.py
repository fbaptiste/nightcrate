"""Tests for stable CI shard selection."""

import pytest

from tests.shard_selection import Shard, ShardItem, parse_shard, select_shard, shard_index


def test_parse_valid_shard():
    assert parse_shard("2/6") == Shard(index=2, total=6)


def test_shards_are_disjoint_and_union_is_everything():
    keys = [f"tests/test_example.py::test_{index}" for index in range(200)]
    items = [ShardItem(key) for key in keys]
    memberships = [
        {key for key, keep in zip(keys, select_shard(items, Shard(index, 7)), strict=True) if keep}
        for index in range(1, 8)
    ]

    assert set().union(*memberships) == set(keys)
    assert sum(len(members) for members in memberships) == len(keys)


def test_group_members_stay_together():
    items = [ShardItem("annual-m42"), ShardItem("ordinary-node"), ShardItem("annual-m42")]
    for index in range(1, 5):
        selected = select_shard(items, Shard(index, 4))
        assert selected[0] == selected[2]


def test_pinned_item_and_its_group_always_land_on_first_shard():
    items = [
        ShardItem("frontend-only", pin_to_first=True),
        ShardItem("frontend-group"),
        ShardItem("frontend-group", pin_to_first=True),
    ]
    for total in (1, 3, 4, 6, 11):
        for index in range(1, total + 1):
            assert select_shard(items, Shard(index, total)) == [index == 1] * 3


@pytest.mark.parametrize("value", ["", "0/3", "4/3", "1/0", "1", "one/two", " 1/3"])
def test_invalid_values_are_refused_clearly(value):
    with pytest.raises(ValueError, match="expected|exceeds"):
        parse_shard(value)


def test_sha256_selection_is_stable():
    assert shard_index("tests/test_example.py::test_one", 6) == 5
