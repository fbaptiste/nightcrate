"""Tests for latitude/longitude sexagesimal formatting."""

import pytest

from nightcrate.services.coordinate_format import format_latitude, format_longitude


class TestFormatLatitude:
    def test_positive_north(self):
        assert format_latitude(33.465) == "33\u00B027\u203254\u2033 N"

    def test_negative_south(self):
        assert format_latitude(-33.465) == "33\u00B027\u203254\u2033 S"

    def test_zero(self):
        # Zero formats as N by the `>= 0` convention.
        assert format_latitude(0.0) == "00\u00B000\u203200\u2033 N"

    def test_single_digit_degree_pads(self):
        assert format_latitude(5.5) == "05\u00B030\u203200\u2033 N"

    def test_single_digit_minute_and_second_pad(self):
        assert format_latitude(33.0681) == "33\u00B004\u203205\u2033 N"

    def test_seconds_round_up_no_60(self):
        # 33.4999999 rounds arcseconds up to 60; astropy must carry into
        # the minute rather than emit "60".
        out = format_latitude(33.4999999)
        assert "60\u2033" not in out
        assert out == "33\u00B030\u203200\u2033 N"

    def test_minute_rollover(self):
        # 33.9999 rounds all the way up to the next degree; no "60′" or
        # "60″" anywhere.
        out = format_latitude(33.9999)
        assert "60\u2032" not in out
        assert "60\u2033" not in out
        assert out == "34\u00B000\u203200\u2033 N"

    def test_boundary_90(self):
        assert format_latitude(90.0) == "90\u00B000\u203200\u2033 N"

    def test_boundary_negative_90(self):
        assert format_latitude(-90.0) == "90\u00B000\u203200\u2033 S"

    @pytest.mark.parametrize("bad", [91.0, -90.1, 180.0, -1000.0])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(ValueError, match="Latitude out of range"):
            format_latitude(bad)


class TestFormatLongitude:
    def test_positive_east(self):
        assert format_longitude(112.074) == "112\u00B004\u203226\u2033 E"

    def test_negative_west(self):
        assert format_longitude(-112.074) == "112\u00B004\u203226\u2033 W"

    def test_zero(self):
        assert format_longitude(0.0) == "00\u00B000\u203200\u2033 E"

    def test_single_digit_degree_pads(self):
        assert format_longitude(5.5) == "05\u00B030\u203200\u2033 E"

    def test_boundary_180_east(self):
        assert format_longitude(180.0) == "180\u00B000\u203200\u2033 E"

    def test_boundary_180_west(self):
        assert format_longitude(-180.0) == "180\u00B000\u203200\u2033 W"

    def test_seconds_round_up_no_60(self):
        out = format_longitude(-112.9999999)
        assert "60\u2033" not in out

    @pytest.mark.parametrize("bad", [180.5, -181.0, 360.0, -500.0])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(ValueError, match="Longitude out of range"):
            format_longitude(bad)
