/**
 * PHD2 dispersion scatter plot — spec §5.3.
 *
 * X = dx, Y = dy, one point per non-null stats sample. 1σ and 2σ
 * dispersion ellipses derived from the 2×2 covariance matrix
 * eigen-decomposition — ellipse axes may be rotated relative to the
 * pixel axes depending on calibration angle. Centroid marker (mean
 * dx, mean dy) — a visible offset from the origin indicates
 * calibration drift.
 *
 * Follows the collapsible + dual-unit pattern of ``StatsPanel``.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useTheme } from "@mui/material/styles";
import type { GuidingSample } from "@/api/phd2";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";

interface Props {
  samples: GuidingSample[];
  arcsecScale: number | null;
  title?: string;
  subtitle?: string;
  collapsible?: boolean;
  defaultExpanded?: boolean;
  height?: number;
}

const MARGIN = { top: 12, right: 12, bottom: 34, left: 44 };
// Square data area — dispersion shape is what we're showing, so
// distortion from a non-square plot would be misleading.
const DEFAULT_HEIGHT = 380;
const MAX_PLOT_WIDTH = 460;

export default function ScatterPlot({
  samples,
  arcsecScale,
  title = "Dispersion",
  subtitle,
  collapsible = true,
  defaultExpanded = true,
  height = DEFAULT_HEIGHT,
}: Props) {
  const theme = useTheme();
  const isDark = theme.palette.mode === "dark";
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(MAX_PLOT_WIDTH);
  const [expanded, setExpanded] = useState(defaultExpanded);
  const isOpen = collapsible ? expanded : true;
  const toggle = () => collapsible && setExpanded((v) => !v);

  useEffect(() => {
    if (!wrapperRef.current) return;
    const obs = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? MAX_PLOT_WIDTH;
      if (w > 0) setWidth(Math.min(MAX_PLOT_WIDTH, w));
    });
    obs.observe(wrapperRef.current);
    return () => obs.disconnect();
  }, []);

  // Points + centroid + covariance, derived once per samples change.
  const stats = useMemo(() => {
    const pts = samples
      .filter(
        (s): s is GuidingSample & { dx_px: number; dy_px: number } =>
          s.dx_px !== null && s.dy_px !== null,
      )
      .map((s) => ({ x: s.dx_px, y: s.dy_px }));
    if (pts.length === 0) {
      return {
        pts: [] as Array<{ x: number; y: number }>,
        centroid: null as { x: number; y: number } | null,
        ellipse: null as EllipseParams | null,
        maxAbs: 1,
      };
    }
    const mx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
    const my = pts.reduce((s, p) => s + p.y, 0) / pts.length;
    let vxx = 0;
    let vyy = 0;
    let vxy = 0;
    for (const p of pts) {
      const dx = p.x - mx;
      const dy = p.y - my;
      vxx += dx * dx;
      vyy += dy * dy;
      vxy += dx * dy;
    }
    vxx /= pts.length;
    vyy /= pts.length;
    vxy /= pts.length;
    // Eigenvalues of [[vxx, vxy], [vxy, vyy]]
    const trace = vxx + vyy;
    const det = vxx * vyy - vxy * vxy;
    const disc = Math.sqrt(Math.max(0, (trace * trace) / 4 - det));
    const l1 = trace / 2 + disc;
    const l2 = trace / 2 - disc;
    const theta = 0.5 * Math.atan2(2 * vxy, vxx - vyy);
    const rx = Math.sqrt(Math.max(0, l1));
    const ry = Math.sqrt(Math.max(0, l2));

    // Symmetric data-space domain sized to enclose the 2σ ellipse
    // plus a margin, or the point cloud — whichever is larger.
    const pointMax = pts.reduce(
      (m, p) => Math.max(m, Math.abs(p.x), Math.abs(p.y)),
      0,
    );
    const ellipseMax = 2 * Math.max(rx, ry);
    const maxAbs = Math.max(0.1, pointMax, ellipseMax) * 1.1;

    return {
      pts,
      centroid: { x: mx, y: my },
      ellipse: { cx: mx, cy: my, rx, ry, theta },
      maxAbs,
    };
  }, [samples]);

  const innerW = Math.max(100, width - MARGIN.left - MARGIN.right);
  const innerH = Math.max(100, height - MARGIN.top - MARGIN.bottom);
  const side = Math.min(innerW, innerH);
  const padX = (innerW - side) / 2;

  const xScale = d3
    .scaleLinear()
    .domain([-stats.maxAbs, stats.maxAbs])
    .range([MARGIN.left + padX, MARGIN.left + padX + side]);
  // Y flipped so +dy goes up (matches CalibrationPlot convention).
  const yScale = d3
    .scaleLinear()
    .domain([-stats.maxAbs, stats.maxAbs])
    .range([MARGIN.top + side, MARGIN.top]);

  const gridColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)";
  const axisColor = isDark ? "rgba(255,255,255,0.6)" : "rgba(0,0,0,0.6)";
  const textColor = isDark ? "rgba(255,255,255,0.87)" : "rgba(0,0,0,0.87)";
  const xTicks = xScale.ticks(5);
  const yTicks = yScale.ticks(5);

  const canArcsec = arcsecScale != null && arcsecScale > 0;
  const formatTick = (v: number): string => {
    if (canArcsec) {
      return `${v.toFixed(1)} (${(v * (arcsecScale as number)).toFixed(2)}″)`;
    }
    return v.toFixed(1);
  };

  const header = (
    <Stack
      direction="row"
      alignItems="center"
      spacing={0.5}
      onClick={toggle}
      sx={{
        cursor: collapsible ? "pointer" : "default",
        userSelect: "none",
        mb: subtitle || !isOpen ? 0.25 : 1,
      }}
    >
      {collapsible && (
        <ExpandMoreIcon
          fontSize="small"
          sx={{
            transition: "transform 120ms ease",
            transform: isOpen ? "rotate(0deg)" : "rotate(-90deg)",
            color: "text.secondary",
          }}
        />
      )}
      <Typography variant="subtitle2">{title}</Typography>
    </Stack>
  );

  const subtitleNode = subtitle && (
    <Typography
      variant="caption"
      color="text.secondary"
      sx={{ display: "block", mb: isOpen ? 1 : 0, pl: collapsible ? 3 : 0 }}
    >
      {subtitle}
    </Typography>
  );

  // Empty-state sentinel — no samples means no scatter, no ellipse.
  if (stats.pts.length === 0) {
    return (
      <Box>
        {header}
        {subtitleNode}
        <Collapse in={isOpen} unmountOnExit>
          <Typography variant="body2" color="text.secondary">
            No dispersion samples in this section.
          </Typography>
        </Collapse>
      </Box>
    );
  }

  const centroidPx = stats.centroid
    ? { x: xScale(stats.centroid.x), y: yScale(stats.centroid.y) }
    : null;

  // Convert the ellipse radii from data-space to pixel-space. Because
  // xScale and yScale share the same domain + side, 1 data unit → the
  // same number of pixels on both axes, so rotation in data-space ==
  // rotation in pixel-space (no anisotropy to correct for).
  const pxPerUnit = side / (2 * stats.maxAbs);
  const ellipseDeg = stats.ellipse
    ? (-stats.ellipse.theta * 180) / Math.PI
    : 0; // SVG y-flip → angle sign flip

  return (
    <Box>
      {header}
      {subtitleNode}
      <Collapse in={isOpen} unmountOnExit>
        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={2}
          alignItems="flex-start"
          sx={{ width: "100%" }}
        >
          <Box
            ref={wrapperRef}
            sx={{ width: "100%", maxWidth: MAX_PLOT_WIDTH, flexShrink: 0 }}
          >
            <svg width={width} height={height} style={{ display: "block" }}>
              {/* Gridlines */}
              {xTicks.map((t) => (
                <line
                  key={`gx-${t}`}
                  x1={xScale(t)}
                  x2={xScale(t)}
                  y1={MARGIN.top}
                  y2={MARGIN.top + side}
                  stroke={gridColor}
                />
              ))}
              {yTicks.map((t) => (
                <line
                  key={`gy-${t}`}
                  x1={MARGIN.left + padX}
                  x2={MARGIN.left + padX + side}
                  y1={yScale(t)}
                  y2={yScale(t)}
                  stroke={gridColor}
                />
              ))}
              {/* Zero axes */}
              <line
                x1={xScale(0)}
                x2={xScale(0)}
                y1={MARGIN.top}
                y2={MARGIN.top + side}
                stroke={axisColor}
              />
              <line
                x1={MARGIN.left + padX}
                x2={MARGIN.left + padX + side}
                y1={yScale(0)}
                y2={yScale(0)}
                stroke={axisColor}
              />
              {/* Scatter points */}
              {stats.pts.map((p, i) => (
                <circle
                  key={i}
                  cx={xScale(p.x)}
                  cy={yScale(p.y)}
                  r={1.5}
                  fill={RIG_BLUE}
                  opacity={0.4}
                />
              ))}
              {/* 1σ + 2σ ellipses */}
              {stats.ellipse && centroidPx && (
                <g
                  transform={`rotate(${ellipseDeg} ${centroidPx.x} ${centroidPx.y})`}
                >
                  <ellipse
                    cx={centroidPx.x}
                    cy={centroidPx.y}
                    rx={stats.ellipse.rx * pxPerUnit}
                    ry={stats.ellipse.ry * pxPerUnit}
                    fill="none"
                    stroke={RIG_BLUE}
                    strokeWidth={1.5}
                    opacity={0.8}
                  />
                  <ellipse
                    cx={centroidPx.x}
                    cy={centroidPx.y}
                    rx={stats.ellipse.rx * pxPerUnit * 2}
                    ry={stats.ellipse.ry * pxPerUnit * 2}
                    fill="none"
                    stroke={RIG_BLUE}
                    strokeWidth={1}
                    strokeDasharray="4 3"
                    opacity={0.5}
                  />
                </g>
              )}
              {/* Centroid marker */}
              {centroidPx && (
                <g>
                  <circle
                    cx={centroidPx.x}
                    cy={centroidPx.y}
                    r={3}
                    fill={RIG_ORANGE}
                  />
                  <circle
                    cx={centroidPx.x}
                    cy={centroidPx.y}
                    r={5}
                    fill="none"
                    stroke={RIG_ORANGE}
                    strokeWidth={1}
                    opacity={0.6}
                  />
                </g>
              )}
              {/* X ticks */}
              {xTicks.map((t) => (
                <text
                  key={`xt-${t}`}
                  x={xScale(t)}
                  y={MARGIN.top + side + 14}
                  fill={textColor}
                  fontSize={9}
                  textAnchor="middle"
                >
                  {t.toFixed(1)}
                </text>
              ))}
              {/* Y ticks */}
              {yTicks.map((t) => (
                <text
                  key={`yt-${t}`}
                  x={MARGIN.left + padX - 6}
                  y={yScale(t)}
                  fill={textColor}
                  fontSize={9}
                  textAnchor="end"
                  dominantBaseline="central"
                >
                  {t.toFixed(1)}
                </text>
              ))}
              {/* Axis labels */}
              <text
                x={(MARGIN.left + padX * 2 + side) / 2}
                y={height - 4}
                fill={textColor}
                fontSize={10}
                textAnchor="middle"
              >
                dx (px{canArcsec ? " / ″" : ""})
              </text>
              <text
                transform={`translate(12, ${MARGIN.top + side / 2}) rotate(-90)`}
                fill={textColor}
                fontSize={10}
                textAnchor="middle"
              >
                dy (px{canArcsec ? " / ″" : ""})
              </text>
            </svg>
          </Box>
          <Box sx={{ flex: 1, minWidth: 180 }}>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              Dispersion shape
            </Typography>
            <Typography variant="body2" sx={{ display: "block", fontVariantNumeric: "tabular-nums" }}>
              Centroid: dx {formatTick(stats.centroid?.x ?? 0)}, dy{" "}
              {formatTick(stats.centroid?.y ?? 0)}
            </Typography>
            {stats.ellipse && (
              <>
                <Typography
                  variant="body2"
                  sx={{ display: "block", fontVariantNumeric: "tabular-nums", mt: 0.5 }}
                >
                  1σ axes: {stats.ellipse.rx.toFixed(3)} × {stats.ellipse.ry.toFixed(3)} px
                </Typography>
                <Typography
                  variant="body2"
                  sx={{ display: "block", fontVariantNumeric: "tabular-nums" }}
                >
                  Principal angle: {((stats.ellipse.theta * 180) / Math.PI).toFixed(1)}°
                </Typography>
              </>
            )}
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mt: 1 }}
            >
              An off-origin centroid suggests calibration drift. A 2σ
              ellipse encloses roughly 95 % of the points.
            </Typography>
          </Box>
        </Stack>
      </Collapse>
    </Box>
  );
}

interface EllipseParams {
  cx: number;
  cy: number;
  rx: number;
  ry: number;
  theta: number;
}
