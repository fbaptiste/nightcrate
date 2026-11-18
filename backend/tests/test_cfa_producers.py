"""CFA headers transcribed from Fred's files; no pixels or personal metadata."""

from nightcrate.services.cfa import pattern_from_fits


def test_zwo_seestar_s30_pro_stored_row_pattern():
    """Physically verified on star-free duo-band NGC 7822 nebulosity."""
    header = {
        "SWCREATE": "ZWO Seestar S30 Pro",
        "BAYERPAT": "GRBG",
        "NAXIS1": 2160,
        "NAXIS2": 3840,
    }
    info = pattern_from_fits(header, 3840)
    assert info is not None
    assert info.pattern.rows == ("GR", "BG")
    assert info.assumptions == ("ROWORDER missing; assumed TOP-DOWN",)


def test_dwarf_mini_stored_row_pattern():
    """The green diagonal is verified; physical red versus blue was inconclusive."""
    header = {"BAYERPAT": "RGGB", "NAXIS1": 1920, "NAXIS2": 1080}
    info = pattern_from_fits(header, 1080)
    assert info is not None
    assert info.pattern.rows == ("RG", "GB")
    assert info.assumptions == ("ROWORDER missing; assumed TOP-DOWN",)


def test_siril_bottom_up_even_height_flips_phase():
    info = pattern_from_fits({"BAYERPAT": "RGGB", "ROWORDER": "BOTTOM-UP"}, 1080)
    assert info is not None
    assert info.pattern.rows == ("GB", "RG")


def test_siril_bottom_up_odd_height_keeps_phase():
    info = pattern_from_fits({"BAYERPAT": "RGGB", "ROWORDER": "BOTTOM-UP"}, 1081)
    assert info is not None
    assert info.pattern.rows == ("RG", "GB")
