from nightcrate.services.native_solver.hints import hints_for


def test_request_hints_override_header():
    cards = [
        {"key": "RA", "value": "05:00:00"},
        {"key": "DEC", "value": "+20:00:00"},
        {"key": "FOCALLEN", "value": "500"},
        {"key": "XPIXSZ", "value": "3.76"},
    ]
    hints = hints_for(
        cards,
        image_height=1200,
        ra_hint=83.0,
        dec_hint=-5.0,
        fov_hint=1.0,
    )
    assert hints.ra_deg == 83.0
    assert hints.dec_deg == -5.0
    assert hints.scale_arcsec == 3.0
    assert hints.position_source == "request"
    assert hints.scale_source == "request"


def test_header_position_and_optical_scale():
    cards = [
        {"key": "OBJCTRA", "value": "05:00:00"},
        {"key": "OBJCTDEC", "value": "-05:30:00"},
        {"key": "FOCALLEN", "value": "500"},
        {"key": "XPIXSZ", "value": "3.76"},
    ]
    hints = hints_for(
        cards,
        image_height=1200,
        ra_hint=None,
        dec_hint=None,
        fov_hint=None,
    )
    assert hints.ra_deg == 75.0
    assert hints.dec_deg == -5.5
    assert hints.scale_arcsec == 206.265 * 3.76 / 500
    assert hints.position_source == "header"
    assert hints.scale_source == "header"


def test_scale_precedence_is_request_then_legacy_fov_then_header():
    cards = [
        {"key": "FOCALLEN", "value": "500"},
        {"key": "YPIXSZ", "value": "4"},
    ]
    explicit = hints_for(
        cards,
        image_height=1000,
        ra_hint=None,
        dec_hint=None,
        scale_hint_arcsec=1.25,
        fov_hint=2.0,
    )
    legacy = hints_for(
        cards,
        image_height=1000,
        ra_hint=None,
        dec_hint=None,
        fov_hint=2.0,
    )
    header = hints_for(
        cards,
        image_height=1000,
        ra_hint=None,
        dec_hint=None,
    )
    assert explicit.scale_arcsec == 1.25
    assert legacy.scale_arcsec == 7.2
    assert header.scale_arcsec == 206.265 * 4 / 500


def test_y_pixel_size_is_used_without_x():
    hints = hints_for(
        [
            {"key": "FOCALLEN", "value": "400"},
            {"key": "YPIXSZ", "value": "2.4"},
        ],
        image_height=1000,
        ra_hint=None,
        dec_hint=None,
    )
    assert hints.scale_arcsec == 206.265 * 2.4 / 400


def test_y_pixel_size_wins_when_x_and_y_differ():
    hints = hints_for(
        [
            {"key": "FOCALLEN", "value": "400"},
            {"key": "XPIXSZ", "value": "9.9"},
            {"key": "YPIXSZ", "value": "2.4"},
        ],
        image_height=1000,
        ra_hint=None,
        dec_hint=None,
    )
    assert hints.scale_arcsec == 206.265 * 2.4 / 400


def test_ignore_flags_override_request_and_header():
    hints = hints_for(
        [
            {"key": "RA", "value": "05:00:00"},
            {"key": "DEC", "value": "+20:00:00"},
            {"key": "FOCALLEN", "value": "500"},
            {"key": "YPIXSZ", "value": "4"},
        ],
        image_height=1000,
        ra_hint=83.0,
        dec_hint=-5.0,
        scale_hint_arcsec=1.25,
        ignore_position=True,
        ignore_scale=True,
    )
    assert hints.ra_deg is None
    assert hints.dec_deg is None
    assert hints.scale_arcsec is None
    assert hints.position_source == "none"
    assert hints.scale_source == "none"
