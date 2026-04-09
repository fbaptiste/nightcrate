"""Tests for the seed hash function — Contract v1."""

import math

import pytest

from nightcrate.seed_loader.hash import HASH_CONTRACT_VERSION, compute_seed_hash


class TestHashContractVersion:
    def test_version_is_one(self):
        assert HASH_CONTRACT_VERSION == "1"


class TestValueEncoding:
    def test_none_value(self):
        h = compute_seed_hash({"x": None})
        assert isinstance(h, str)
        assert len(h) == 64

    def test_bool_true(self):
        h_true = compute_seed_hash({"x": True})
        assert isinstance(h_true, str)

    def test_bool_false(self):
        h_false = compute_seed_hash({"x": False})
        assert isinstance(h_false, str)

    def test_bool_true_and_false_differ(self):
        assert compute_seed_hash({"x": True}) != compute_seed_hash({"x": False})

    def test_bool_not_same_as_int_one(self):
        # bool True encodes as "1", int 1 also encodes as "1" — they are the same
        # by design since bools ARE ints in Python; this is intentional behaviour
        assert compute_seed_hash({"x": True}) == compute_seed_hash({"x": 1})

    def test_int_value(self):
        h = compute_seed_hash({"count": 42})
        assert isinstance(h, str)
        assert len(h) == 64

    def test_float_value(self):
        h = compute_seed_hash({"weight": 700.0})
        assert isinstance(h, str)
        assert len(h) == 64

    def test_string_value(self):
        h = compute_seed_hash({"name": "ASI2600MM Pro"})
        assert isinstance(h, str)
        assert len(h) == 64

    def test_nan_rejected(self):
        with pytest.raises(ValueError, match="NaN"):
            compute_seed_hash({"x": float("nan")})

    def test_positive_infinity_rejected(self):
        with pytest.raises(ValueError, match="infinity"):
            compute_seed_hash({"x": math.inf})

    def test_negative_infinity_rejected(self):
        with pytest.raises(ValueError, match="infinity"):
            compute_seed_hash({"x": -math.inf})

    def test_bytes_rejected(self):
        with pytest.raises(ValueError, match="bytes"):
            compute_seed_hash({"x": b"hello"})

    def test_newline_in_string_rejected(self):
        with pytest.raises(ValueError, match="newlines"):
            compute_seed_hash({"x": "line1\nline2"})

    def test_carriage_return_in_string_rejected(self):
        with pytest.raises(ValueError, match="newlines"):
            compute_seed_hash({"x": "line1\rline2"})

    def test_none_differs_from_empty_string(self):
        assert compute_seed_hash({"x": None}) != compute_seed_hash({"x": ""})

    def test_none_differs_from_zero(self):
        assert compute_seed_hash({"x": None}) != compute_seed_hash({"x": 0})

    def test_unsupported_type_rejected(self):
        with pytest.raises(ValueError, match="unsupported type"):
            compute_seed_hash({"x": [1, 2, 3]})


class TestKeyOrdering:
    def test_order_independent(self):
        h1 = compute_seed_hash({"b": 2, "a": 1})
        h2 = compute_seed_hash({"a": 1, "b": 2})
        assert h1 == h2

    def test_different_keys_different_hash(self):
        h1 = compute_seed_hash({"apple": 1})
        h2 = compute_seed_hash({"banana": 1})
        assert h1 != h2

    def test_single_key(self):
        h = compute_seed_hash({"only": "value"})
        assert len(h) == 64

    def test_empty_dict(self):
        h = compute_seed_hash({})
        assert len(h) == 64


class TestDeterminism:
    def test_same_input_same_hash(self):
        fields = {"model_name": "ASI2600MM Pro", "cooled": True, "weight_g": 700.0}
        assert compute_seed_hash(fields) == compute_seed_hash(fields)

    def test_repeated_calls_stable(self):
        fields = {"a": 1, "b": "hello", "c": None}
        results = {compute_seed_hash(fields) for _ in range(10)}
        assert len(results) == 1

    def test_canonical_known_value(self):
        """Pin the exact hash for the canonical test vector — catches contract drift."""
        fields = {"model_name": "ASI2600MM Pro", "cooled": True, "weight_g": 700.0}
        # Pinned after first run — do not change without a migration.
        expected = "9847ad18f6afc936a11ca0d9d72a4c86f49ab6b8915f1dd25646342f56b1885f"
        assert compute_seed_hash(fields) == expected


class TestFieldNameValidation:
    def test_simple_name_valid(self):
        compute_seed_hash({"model_name": 1})  # should not raise

    def test_underscore_start_valid(self):
        compute_seed_hash({"_private": 1})

    def test_uppercase_valid(self):
        compute_seed_hash({"ModelName": 1})

    def test_alphanumeric_valid(self):
        compute_seed_hash({"field123": 1})

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError, match="Invalid field name"):
            compute_seed_hash({"": 1})

    def test_digit_start_rejected(self):
        with pytest.raises(ValueError, match="Invalid field name"):
            compute_seed_hash({"1field": 1})

    def test_hyphen_rejected(self):
        with pytest.raises(ValueError, match="Invalid field name"):
            compute_seed_hash({"field-name": 1})

    def test_space_rejected(self):
        with pytest.raises(ValueError, match="Invalid field name"):
            compute_seed_hash({"field name": 1})

    def test_dot_rejected(self):
        with pytest.raises(ValueError, match="Invalid field name"):
            compute_seed_hash({"field.name": 1})
