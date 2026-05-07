import { useState } from "react";
import Box from "@mui/material/Box";
import Fade from "@mui/material/Fade";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import type { SampleGridResult, SampleSquare, StarMeasurement, AberrationMetric } from "@/api/aberration";
import { regionCropUrl } from "@/api/aberration";
import { monoFontFamily } from "@/theme/theme";

/** Viridis-inspired colorblind-safe scale (5 stops). */
const VIRIDIS = ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"];

function viridisColor(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const idx = clamped * (VIRIDIS.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.min(lo + 1, VIRIDIS.length - 1);
  const frac = idx - lo;
  const lerp = (a: number, b: number) => Math.round(a + (b - a) * frac);
  const parse = (hex: string) => [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
  const [r1, g1, b1] = parse(VIRIDIS[lo]);
  const [r2, g2, b2] = parse(VIRIDIS[hi]);
  return `rgb(${lerp(r1, r2)}, ${lerp(g1, g2)}, ${lerp(b1, b2)})`;
}

function getMetricValue(sq: SampleSquare, metric: AberrationMetric): number | null {
  switch (metric) {
    case "eccentricity": return sq.median_eccentricity;
    case "fwhm": return sq.median_fwhm;
    case "hfr": return sq.median_hfr;
    case "peak_adu": return null;
    case "elongation_angle": return sq.median_elongation_angle;
  }
}

function formatMetric(value: number | null, metric: AberrationMetric): string {
  if (value == null) return "—";
  switch (metric) {
    case "eccentricity": return value.toFixed(3);
    case "fwhm": return value.toFixed(2);
    case "hfr": return value.toFixed(2);
    case "peak_adu": return value.toFixed(0);
    case "elongation_angle": return `${value.toFixed(0)}°`;
  }
}

const METRIC_LABELS: Record<AberrationMetric, string> = {
  eccentricity: "Eccentricity",
  fwhm: "FWHM",
  hfr: "HFR",
  peak_adu: "Peak ADU",
  elongation_angle: "Elong. Angle",
};

function buildTooltip(sq: SampleSquare): string {
  if (sq.star_count === 0) return "No isolated stars in this region";
  const lines = [
    `Stars: ${sq.star_count}`,
    `Med FWHM: ${sq.median_fwhm?.toFixed(2) ?? "—"}`,
    `Med Ecc: ${sq.median_eccentricity?.toFixed(3) ?? "—"}`,
    `Med HFR: ${sq.median_hfr?.toFixed(2) ?? "—"}`,
    `Mean FWHM: ${sq.mean_fwhm?.toFixed(2) ?? "—"}`,
    `Std FWHM: ${sq.std_fwhm?.toFixed(3) ?? "—"}`,
  ];
  if (sq.median_elongation_angle != null) {
    lines.push(`Med Angle: ${sq.median_elongation_angle.toFixed(0)}°`);
  }
  return lines.join("\n");
}

/** Color legend bar for the viridis scale. */
function ColorLegend({ metric, minVal, maxVal }: { metric: AberrationMetric; minVal: number; maxVal: number }) {
  const stops = VIRIDIS.map((c, i) => `${c} ${(i / (VIRIDIS.length - 1)) * 100}%`).join(", ");
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, pb: 1 }}>
      <Typography sx={{ fontSize: "0.55rem", fontFamily: monoFontFamily, color: "text.secondary" }}>
        {formatMetric(minVal, metric)}
      </Typography>
      <Box
        sx={{
          flex: 1,
          height: 8,
          borderRadius: 0.5,
          background: `linear-gradient(to right, ${stops})`,
        }}
      />
      <Typography sx={{ fontSize: "0.55rem", fontFamily: monoFontFamily, color: "text.secondary" }}>
        {formatMetric(maxVal, metric)}
      </Typography>
      <Typography sx={{ fontSize: "0.55rem", color: "text.secondary", ml: 0.5 }}>
        {METRIC_LABELS[metric]}
      </Typography>
    </Box>
  );
}

const PREVIEW_SIZE = 640;

interface Props {
  grid: SampleGridResult;
  squares: SampleSquare[];
  stars: StarMeasurement[];
  path: string;
  hdu: number;
  metric: AberrationMetric;
  selectedSquare: SampleSquare | null;
  onSquareClick: (sq: SampleSquare) => void;
}

export function CropGrid({ grid, squares, stars, path, hdu, metric, selectedSquare, onSquareClick }: Props) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const [previewSquare, setPreviewSquare] = useState<SampleSquare | null>(null);
  const [showCircles, setShowCircles] = useState(true);
  const [hoveredStar, setHoveredStar] = useState<{ star: StarMeasurement; x: number; y: number } | null>(null);

  function handleTileClick(sq: SampleSquare) {
    onSquareClick(sq);
    if (previewSquare?.row === sq.row && previewSquare?.col === sq.col) {
      setPreviewSquare(null);
    } else {
      setPreviewSquare(sq);
    }
  }

  function closePreview() {
    setPreviewSquare(null);
  }

  // Compute metric range for color scale
  const values = squares
    .map((sq) => getMetricValue(sq, metric))
    .filter((v): v is number => v != null);
  const minVal = values.length > 0 ? Math.min(...values) : 0;
  const maxVal = values.length > 0 ? Math.max(...values) : 1;
  const range = maxVal - minVal || 1;

  // Stars in the preview square (mapped to preview coordinates)
  const previewStars = previewSquare
    ? previewSquare.star_indices.map((i) => stars[i]).filter(Boolean)
    : [];
  const pSq = previewSquare;
  const pW = pSq ? pSq.x1 - pSq.x0 : 1;
  const pH = pSq ? pSq.y1 - pSq.y0 : 1;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", flexGrow: 1, position: "relative" }}>
      {/* Legend */}
      <ColorLegend metric={metric} minVal={minVal} maxVal={maxVal} />

      {/* Centered preview — no blocking overlay, positioned via pointer-events */}
      <Fade in={previewSquare != null} timeout={200}>
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            zIndex: 1200,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
          }}
        >
          {previewSquare && (
            <Box
              onClick={(e) => e.stopPropagation()}
              sx={{
                pointerEvents: "auto",
                width: PREVIEW_SIZE,
                maxWidth: "90%",
                maxHeight: "90%",
                bgcolor: "#000000",
                border: 3,
                borderColor: "#ffffff",
                borderRadius: 1,
                overflow: "hidden",
                boxShadow: 12,
                display: "flex",
                flexDirection: "column",
                cursor: "default",
              }}
            >
              {/* Image area with SVG overlay */}
              <Box sx={{ position: "relative", width: "100%", height: PREVIEW_SIZE, flexShrink: 0 }}>
              {/* Crop image */}
              <Box
                component="img"
                src={regionCropUrl(path, hdu, previewSquare.x0, previewSquare.y0, previewSquare.x1, previewSquare.y1)}
                sx={{
                  width: "100%",
                  height: "100%",
                  objectFit: "contain",
                  imageRendering: "pixelated",
                }}
              />
              {/* Star ellipse overlay */}
              {showCircles && (
                <svg
                  style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
                  viewBox={`0 0 ${pW} ${pH}`}
                >
                  {previewStars.map((s, i) => {
                    const cx = s.x - previewSquare.x0;
                    const cy = s.y - previewSquare.y0;
                    const rx = Math.max(s.semi_major * 3, 6);
                    const ry = Math.max(s.semi_minor * 3, 6);
                    const fs = Math.max(pW * 0.018, 8);
                    const angleRad = s.elongation_angle_deg * Math.PI / 180;
                    // Major axis direction
                    const majDx = Math.cos(angleRad);
                    const majDy = Math.sin(angleRad);
                    // Perpendicular (minor axis direction) — offset line below ellipse
                    const perpDx = -majDy;
                    const perpDy = majDx;
                    // Line on one side, label on the opposite side
                    const lineOffset = ry + 8;
                    const labelOffset = ry + fs + 10;
                    // Choose which perp direction has more space for the line
                    const belowY = cy + perpDy * lineOffset;
                    const placeLineBelow = belowY >= 0 && belowY < pH;
                    const lineSign = placeLineBelow ? 1 : -1;
                    const labelSign = -lineSign; // label on opposite side
                    // Line center
                    const lineCx = cx + lineSign * perpDx * lineOffset;
                    const lineCy = cy + lineSign * perpDy * lineOffset;
                    // Label center
                    const labelCx = cx + labelSign * perpDx * labelOffset;
                    const labelCy = cy + labelSign * perpDy * labelOffset;
                    // Line half-length along major axis
                    const halfLine = rx * 1.5 + 18;
                    const lx1 = lineCx - majDx * halfLine;
                    const ly1 = lineCy - majDy * halfLine;
                    const lx2 = lineCx + majDx * halfLine;
                    const ly2 = lineCy + majDy * halfLine;
                    return (
                      <g
                        key={i}
                        style={{ pointerEvents: "all", cursor: "crosshair" }}
                        onMouseEnter={(e) => {
                          const svg = e.currentTarget.closest("svg");
                          if (!svg) return;
                          const rect = svg.getBoundingClientRect();
                          const px = (cx / pW) * rect.width + rect.left;
                          const py = (cy / pH) * rect.height + rect.top;
                          setHoveredStar({ star: s, x: px, y: py });
                        }}
                        onMouseLeave={() => setHoveredStar(null)}
                        onTouchStart={(e) => {
                          e.preventDefault();
                          const svg = e.currentTarget.closest("svg");
                          if (!svg) return;
                          const rect = svg.getBoundingClientRect();
                          const px = (cx / pW) * rect.width + rect.left;
                          const py = (cy / pH) * rect.height + rect.top;
                          setHoveredStar({ star: s, x: px, y: py });
                        }}
                        onTouchEnd={() => setHoveredStar(null)}
                      >
                        {/* Invisible hit area for easier hover */}
                        <ellipse
                          cx={cx}
                          cy={cy}
                          rx={rx + 5}
                          ry={ry + 5}
                          transform={`rotate(${s.elongation_angle_deg} ${cx} ${cy})`}
                          fill="transparent"
                          stroke="none"
                        />
                        <ellipse
                          cx={cx}
                          cy={cy}
                          rx={rx}
                          ry={ry}
                          transform={`rotate(${s.elongation_angle_deg} ${cx} ${cy})`}
                          fill="none"
                          stroke="#5ec962"
                          strokeWidth={1.5}
                          opacity={0.8}
                        />
                        {/* Dotted line showing major axis direction */}
                        <line
                          x1={lx1} y1={ly1} x2={lx2} y2={ly2}
                          stroke="#ff9800"
                          strokeWidth={3}
                          strokeDasharray="5 3"
                        />
                        {/* Label on opposite side */}
                        <text
                          x={labelCx}
                          y={labelCy + fs * 0.35}
                          fill="#5ec962"
                          fontSize={fs}
                          fontFamily="monospace"
                          textAnchor="middle"
                          opacity={0.9}
                        >
                          {`e: ${s.eccentricity.toFixed(2)}`}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              )}
              {/* Star hover tooltip with zoomed crop */}
              {hoveredStar && (() => {
                const hs = hoveredStar.star;
                const cropR = Math.max(Math.round(hs.fwhm * 1.8), 8);
                const sx0 = Math.max(0, Math.round(hs.x) - cropR);
                const sy0 = Math.max(0, Math.round(hs.y) - cropR);
                const sx1 = Math.round(hs.x) + cropR;
                const sy1 = Math.round(hs.y) + cropR;
                return (
                  <Box
                    sx={{
                      position: "fixed",
                      left: hoveredStar.x + 16,
                      top: hoveredStar.y - 60,
                      bgcolor: "rgba(0,0,0,0.95)",
                      border: 1,
                      borderColor: "#5ec962",
                      borderRadius: 1,
                      zIndex: 1400,
                      pointerEvents: "none",
                      display: "flex",
                      gap: 1,
                      p: 0.75,
                      alignItems: "center",
                    }}
                  >
                    <Box
                      component="img"
                      src={regionCropUrl(path, hdu, sx0, sy0, sx1, sy1)}
                      sx={{
                        width: 216,
                        height: 216,
                        objectFit: "contain",
                        imageRendering: "pixelated",
                        borderRadius: 0.5,
                        flexShrink: 0,
                      }}
                    />
                    <Box sx={{ whiteSpace: "pre-line", fontFamily: monoFontFamily, fontSize: "0.6rem", color: "text.secondary" }}>
                      {[
                        `FWHM: ${hs.fwhm.toFixed(2)}`,
                        `Ecc: ${hs.eccentricity.toFixed(3)}`,
                        `HFR: ${hs.hfr.toFixed(2)}`,
                        `SNR: ${hs.snr.toFixed(0)}`,
                        `Peak: ${hs.peak_adu.toFixed(2)}`,
                        `Angle: ${hs.elongation_angle_deg.toFixed(0)}°`,
                        `a/b: ${hs.semi_major.toFixed(2)}/${hs.semi_minor.toFixed(2)}`,
                      ].join("\n")}
                    </Box>
                  </Box>
                );
              })()}
              {/* Close button */}
              <IconButton
                size="small"
                onClick={(e) => { e.stopPropagation(); closePreview(); }}
                sx={{
                  position: "absolute",
                  top: 4,
                  right: 4,
                  bgcolor: "rgba(0,0,0,0.6)",
                  color: "text.secondary",
                  p: 0.25,
                  "&:hover": { bgcolor: "rgba(0,0,0,0.8)", color: "text.primary" },
                }}
              >
                <CloseIcon sx={{ fontSize: 16 }} />
              </IconButton>
              </Box>{/* end image area */}
              {/* Stats bar below image */}
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1,
                  px: 1,
                  py: 0.5,
                  bgcolor: "rgba(0,0,0,0.9)",
                  borderTop: 1,
                  borderColor: "divider",
                }}
              >
                <Box sx={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 2, rowGap: 0, fontSize: "0.6rem", fontFamily: monoFontFamily, color: "text.secondary" }}>
                  <span>Stars: {previewSquare.star_count}</span>
                  <span>Med Ecc: {previewSquare.median_eccentricity?.toFixed(3) ?? "—"}</span>
                  <span>Med FWHM: {previewSquare.median_fwhm?.toFixed(2) ?? "—"}</span>
                  <span>Med HFR: {previewSquare.median_hfr?.toFixed(2) ?? "—"}</span>
                  <span>Mean FWHM: {previewSquare.mean_fwhm?.toFixed(2) ?? "—"}</span>
                  <span>Std FWHM: {previewSquare.std_fwhm?.toFixed(3) ?? "—"}</span>
                </Box>
                <Tooltip title={showCircles ? "Hide star markers" : "Show star markers"} arrow>
                  <IconButton
                    size="small"
                    onClick={(e) => { e.stopPropagation(); setShowCircles((v) => !v); }}
                    sx={{
                      color: showCircles ? "#5ec962" : "text.secondary",
                      p: 0.5,
                      flexShrink: 0,
                    }}
                  >
                    <RadioButtonUncheckedIcon sx={{ fontSize: 18 }} />
                  </IconButton>
                </Tooltip>
              </Box>
            </Box>
          )}
        </Box>
      </Fade>

      {/* Grid — fills available space */}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: `repeat(${grid.cols}, 1fr)`,
          gridTemplateRows: `repeat(${grid.rows}, 1fr)`,
          gap: "6px",
          flexGrow: 1,
          p: 1,
        }}
      >
        {squares.map((sq) => {
          const key = `${sq.row}-${sq.col}`;
          const metricVal = getMetricValue(sq, metric);
          const t = metricVal != null ? (metricVal - minVal) / range : 0;
          const isHovered = hoveredKey === key;
          const isSelected = selectedSquare?.row === sq.row && selectedSquare?.col === sq.col;
          const borderColor = sq.star_count > 0 ? viridisColor(t) : "rgba(255,255,255,0.1)";

          return (
            <Tooltip
              key={key}
              title={<Box sx={{ whiteSpace: "pre-line", fontFamily: monoFontFamily, fontSize: "0.65rem" }}>{buildTooltip(sq)}</Box>}
              arrow
              placement="top"
              enterDelay={200}
            >
              <Box
                onClick={() => handleTileClick(sq)}
                onMouseEnter={() => setHoveredKey(key)}
                onMouseLeave={() => setHoveredKey(null)}
                sx={{
                  position: "relative",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  bgcolor: "#000000",
                  border: 3,
                  borderColor: isSelected ? "#ffffff" : isHovered ? "rgba(255,255,255,0.6)" : borderColor,
                  borderRadius: 1,
                  cursor: "pointer",
                  overflow: "hidden",
                  transition: "border-color 0.15s",
                  opacity: sq.star_count > 0 ? 1 : 0.25,
                }}
              >
                {/* Actual image region crop */}
                <Box
                  component="img"
                  src={regionCropUrl(path, hdu, sq.x0, sq.y0, sq.x1, sq.y1)}
                  sx={{
                    position: "absolute",
                    inset: 0,
                    width: "100%",
                    height: "100%",
                    objectFit: "contain",
                    imageRendering: "auto",
                  }}
                />
                {/* Metric bar at bottom */}
                <Box
                  sx={{
                    position: "absolute",
                    bottom: 0,
                    left: 0,
                    right: 0,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    px: 0.5,
                    py: 0.25,
                    bgcolor: "rgba(0,0,0,0.65)",
                  }}
                >
                  <Typography
                    sx={{
                      fontSize: "0.6rem",
                      fontFamily: monoFontFamily,
                      fontWeight: 600,
                      color: "rgba(255,255,255,0.6)",
                    }}
                  >
                    {formatMetric(metricVal, metric)}
                  </Typography>
                  <Typography sx={{ fontSize: "0.6rem", color: "rgba(255,255,255,0.6)" }}>
                    {sq.star_count}★
                  </Typography>
                </Box>
              </Box>
            </Tooltip>
          );
        })}
      </Box>
    </Box>
  );
}
