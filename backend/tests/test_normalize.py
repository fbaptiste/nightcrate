"""Tests for data normalization."""

import numpy as np
import pytest

from nightcrate.services.fits import _normalize_to_01


class TestNormalizeTo01:
    def test_uint16(self):
        data = np.array([0, 32768, 65535], dtype=np.uint16)
        result = _normalize_to_01(data)
        assert result.dtype == np.float64
        assert result[0] == pytest.approx(0.0)
        assert result[1] == pytest.approx(32768 / 65535)
        assert result[2] == pytest.approx(1.0)

    def test_uint32(self):
        data = np.array([0, 4294967295], dtype=np.uint32)
        result = _normalize_to_01(data)
        assert result[0] == pytest.approx(0.0)
        assert result[1] == pytest.approx(1.0)

    def test_int16(self):
        data = np.array([-32768, 0, 32767], dtype=np.int16)
        result = _normalize_to_01(data)
        assert result[0] == pytest.approx(0.0)
        assert result[2] == pytest.approx(1.0)
        assert 0.0 < result[1] < 1.0

    def test_float32_already_normalized(self):
        data = np.array([0.0, 0.5, 1.0], dtype=np.float32)
        result = _normalize_to_01(data)
        assert result[0] == pytest.approx(0.0)
        assert result[1] == pytest.approx(0.5)
        assert result[2] == pytest.approx(1.0)

    def test_float32_exceeds_one(self):
        data = np.array([0.0, 50.0, 100.0], dtype=np.float32)
        result = _normalize_to_01(data)
        assert result[0] == pytest.approx(0.0)
        assert result[2] == pytest.approx(1.0)
        assert result[1] == pytest.approx(0.5)

    def test_float_negative_clipped(self):
        data = np.array([-0.5, 0.0, 0.5], dtype=np.float64)
        result = _normalize_to_01(data)
        assert result[0] >= 0.0

    def test_preserves_2d_shape(self):
        data = np.zeros((10, 20), dtype=np.uint16)
        result = _normalize_to_01(data)
        assert result.shape == (10, 20)
