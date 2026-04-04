"""Aberration analysis — star detection, measurement, and sample square aggregation."""

from __future__ import annotations

import numpy as np
import sep
from pydantic import BaseModel


class DetectionSettings(BaseModel):
    """Configurable parameters for star detection."""

    detection_threshold: float = 5.0
    min_star_snr: float = 10.0
    max_star_peak_adu: float | None = None
    min_star_fwhm_px: float = 3.0
    max_star_fwhm_px: float = 30.0
    edge_margin_px: int = 10
    aperture_radius_factor: float = 3.0
    hfr_max_radius: float = 20.0
    max_semi_major_px: float = 15.0  # reject extended objects (galaxy cores, nebula knots)
    min_separation_px: float = 20.0  # reject stars with a neighbor closer than this


class StarMeasurement(BaseModel):
    """Per-star metrics from detection."""

    x: float
    y: float
    fwhm: float
    hfr: float
    eccentricity: float
    elongation_angle_deg: float
    peak_adu: float
    flux: float
    snr: float
    semi_major: float
    semi_minor: float
    flag: int = 0  # sep extraction flag (non-zero = blended/crowded)


class AnalysisResult(BaseModel):
    """Full analysis output — star list plus global stats."""

    stars: list[StarMeasurement]
    star_count: int
    image_width: int
    image_height: int
    median_fwhm: float | None = None
    median_hfr: float | None = None
    median_eccentricity: float | None = None
    settings: DetectionSettings


class SampleSquare(BaseModel):
    """One sample square in the field — aggregated stats for isolated stars within."""

    row: int
    col: int
    # Square position in image coordinates (pixels)
    x0: int
    y0: int
    x1: int
    y1: int
    # Stars found in this square
    star_count: int
    star_indices: list[int]
    # Aggregated metrics (None if no isolated stars)
    median_fwhm: float | None = None
    mean_fwhm: float | None = None
    std_fwhm: float | None = None
    median_eccentricity: float | None = None
    median_hfr: float | None = None
    median_elongation_angle: float | None = None


class SampleGridResult(BaseModel):
    """Sample grid output — evenly spaced squares across the field."""

    samples_across: int
    rows: int
    cols: int
    square_size: int  # pixels in original image
    squares: list[SampleSquare]


def detect_stars(
    data: np.ndarray,
    settings: DetectionSettings | None = None,
) -> AnalysisResult:
    """Detect isolated point sources and measure per-star metrics.

    Filters out extended objects (galaxy cores, nebula knots) and blended
    sources to ensure only genuine isolated stars are measured.

    Args:
        data: 2D float64 array normalized to [0, 1].
        settings: Detection parameters. Uses defaults if None.

    Returns:
        AnalysisResult with star measurements and global stats.
    """
    if settings is None:
        settings = DetectionSettings()

    height, width = data.shape
    img = np.ascontiguousarray(data, dtype=np.float64)

    bkg = sep.Background(img)
    img_sub = img - bkg

    sep.set_extract_pixstack(1_000_000)

    # On [0,1] normalized data the global RMS can be very small, making the
    # absolute detection threshold too low and flooding sep with nebulosity
    # pixels.  If extraction overflows the pixstack, retry with progressively
    # higher thresholds before giving up.
    thresh = settings.detection_threshold
    objects = None
    for attempt in range(4):
        try:
            objects = sep.extract(img_sub, thresh=thresh, err=bkg.globalrms)
            break
        except Exception as exc:
            if "pixel buffer full" in str(exc) and attempt < 3:
                thresh *= 2  # double the threshold and retry
            else:
                raise
    assert objects is not None

    if len(objects) == 0:
        return AnalysisResult(
            stars=[],
            star_count=0,
            image_width=width,
            image_height=height,
            settings=settings,
        )

    stars: list[StarMeasurement] = []
    xs = objects["x"]
    ys = objects["y"]
    as_ = objects["a"]
    bs = objects["b"]
    thetas = objects["theta"]
    peaks = objects["peak"]
    flags = objects["flag"]

    rmax = np.full(len(objects), settings.hfr_max_radius)
    hfrs, _ = sep.flux_radius(img_sub, xs, ys, rmax, 0.5)

    radii = settings.aperture_radius_factor * as_
    radii = np.clip(radii, 3.0, 50.0)
    flux_arr, fluxerr_arr, _ = sep.sum_circle(
        img_sub,
        xs,
        ys,
        radii,
        err=bkg.globalrms,
    )

    for i in range(len(objects)):
        x, y = float(xs[i]), float(ys[i])
        a, b = float(as_[i]), float(bs[i])
        flag = int(flags[i])

        # Edge exclusion
        margin = settings.edge_margin_px
        if x < margin or x > width - margin or y < margin or y > height - margin:
            continue

        # Ensure a >= b
        if b > a:
            a, b = b, a

        # Reject extended objects (galaxy cores, nebula knots)
        if a > settings.max_semi_major_px:
            continue

        # Reject blended/crowded sources (sep flag bits)
        if flag & 0x02:  # object is blended with another
            continue

        ecc = float(np.sqrt(1 - (b / a) ** 2)) if a > 0 else 0.0
        fwhm = 2.0 * np.sqrt(np.log(2)) * np.sqrt(a**2 + b**2)
        angle_deg = float(np.degrees(thetas[i])) % 180

        hfr = float(hfrs[i])
        peak = float(peaks[i])
        flux = float(flux_arr[i])
        fluxerr = float(fluxerr_arr[i])
        snr = flux / fluxerr if fluxerr > 0 else 0.0

        if snr < settings.min_star_snr:
            continue
        if fwhm < settings.min_star_fwhm_px or fwhm > settings.max_star_fwhm_px:
            continue
        if settings.max_star_peak_adu is not None and peak > settings.max_star_peak_adu:
            continue

        stars.append(
            StarMeasurement(
                x=round(x, 2),
                y=round(y, 2),
                fwhm=round(fwhm, 3),
                hfr=round(hfr, 3),
                eccentricity=round(ecc, 4),
                elongation_angle_deg=round(angle_deg, 1),
                peak_adu=round(peak, 4),
                flux=round(flux, 2),
                snr=round(snr, 1),
                semi_major=round(a, 3),
                semi_minor=round(b, 3),
                flag=flag,
            )
        )

    # Isolation filter: reject stars with a neighbor closer than min_separation_px
    if settings.min_separation_px > 0 and len(stars) > 1:
        coords = np.array([(s.x, s.y) for s in stars])
        isolated: list[StarMeasurement] = []
        min_sep2 = settings.min_separation_px**2
        for idx_s, s in enumerate(stars):
            diffs = coords - np.array([s.x, s.y])
            dists2 = diffs[:, 0] ** 2 + diffs[:, 1] ** 2
            dists2[idx_s] = np.inf  # exclude self
            if np.min(dists2) >= min_sep2:
                isolated.append(s)
        stars = isolated

    median_fwhm = None
    median_hfr = None
    median_ecc = None
    if stars:
        median_fwhm = round(float(np.median([s.fwhm for s in stars])), 3)
        median_hfr = round(float(np.median([s.hfr for s in stars])), 3)
        median_ecc = round(float(np.median([s.eccentricity for s in stars])), 4)

    return AnalysisResult(
        stars=stars,
        star_count=len(stars),
        image_width=width,
        image_height=height,
        median_fwhm=median_fwhm,
        median_hfr=median_hfr,
        median_eccentricity=median_ecc,
        settings=settings,
    )


def compute_sample_grid(
    analysis: AnalysisResult,
    samples_across: int = 5,
) -> SampleGridResult:
    """Place evenly-spaced sample squares across the image and aggregate star metrics.

    The square size is computed relative to the image: roughly
    image_width / (samples_across * 1.5), so squares are large enough
    to contain multiple stars but leave gaps between them.

    Args:
        analysis: Result from detect_stars() (isolated stars only).
        samples_across: Number of sample squares horizontally.

    Returns:
        SampleGridResult with per-square aggregated metrics.
    """
    w, h = analysis.image_width, analysis.image_height

    # Square size: large enough for multiple stars, with gaps
    square_size = max(64, int(w / (samples_across * 1.5)))

    # Compute grid layout — evenly spaced with margins
    cols = samples_across
    rows = max(1, round(cols * h / w))

    # Spacing: distribute squares evenly across the image
    # Each square center is at (margin + i * step, margin + j * step)
    x_step = (w - square_size) / max(cols - 1, 1) if cols > 1 else 0
    y_step = (h - square_size) / max(rows - 1, 1) if rows > 1 else 0
    x_margin = (w - square_size - x_step * (cols - 1)) / 2 if cols > 1 else (w - square_size) / 2
    y_margin = (h - square_size - y_step * (rows - 1)) / 2 if rows > 1 else (h - square_size) / 2

    squares: list[SampleSquare] = []
    for r in range(rows):
        for c in range(cols):
            cx = int(x_margin + c * x_step + square_size / 2)
            cy = int(y_margin + r * y_step + square_size / 2)
            half = square_size // 2
            x0 = max(0, cx - half)
            y0 = max(0, cy - half)
            x1 = min(w, cx + half)
            y1 = min(h, cy + half)

            # Find stars within this square
            indices = [i for i, s in enumerate(analysis.stars) if x0 <= s.x < x1 and y0 <= s.y < y1]

            if not indices:
                squares.append(
                    SampleSquare(
                        row=r,
                        col=c,
                        x0=x0,
                        y0=y0,
                        x1=x1,
                        y1=y1,
                        star_count=0,
                        star_indices=[],
                    )
                )
                continue

            zone_stars = [analysis.stars[i] for i in indices]
            fwhms = np.array([s.fwhm for s in zone_stars])
            eccs = np.array([s.eccentricity for s in zone_stars])
            hfrs = np.array([s.hfr for s in zone_stars])
            angles = np.array([s.elongation_angle_deg for s in zone_stars])

            squares.append(
                SampleSquare(
                    row=r,
                    col=c,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                    star_count=len(indices),
                    star_indices=indices,
                    median_fwhm=round(float(np.median(fwhms)), 3),
                    mean_fwhm=round(float(np.mean(fwhms)), 3),
                    std_fwhm=round(float(np.std(fwhms)), 3) if len(fwhms) > 1 else 0.0,
                    median_eccentricity=round(float(np.median(eccs)), 4),
                    median_hfr=round(float(np.median(hfrs)), 3),
                    median_elongation_angle=round(float(np.median(angles)), 1),
                )
            )

    return SampleGridResult(
        samples_across=samples_across,
        rows=rows,
        cols=cols,
        square_size=square_size,
        squares=squares,
    )
