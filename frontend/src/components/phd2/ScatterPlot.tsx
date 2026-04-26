/**
 * PHD2 dispersion scatter plot.
 *
 * X = dx, Y = dy, one point per non-null stats sample. 1σ and 2σ
 * dispersion ellipses are drawn around the centroid; the ellipse
 * rotation uses ``θ = atan2(cov_xy, var_x)`` (close to but not
 * exactly the textbook PCA rotation — close enough for the typical
 * guide-log scatter shape, simpler to compute).
 *
 * Centroid marker (mean dx, mean dy) — a visible offset from the
 * origin indicates calibration drift.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useTheme } from "@mui/material/styles";
import type { GuidingSample } from "@/api/phd2";
import { RIG_BLUE } from "@/lib/rigColors";

const ELLIPSE_COLOR = "#4db6ac";

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
const DEFAULT_HEIGHT = 380;
const MAX_PLOT_WIDTH = 460;

type Unit = "px" | "arcsec";

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
  const canArcsec = arcsecScale != null && arcsecScale > 0;
  const [unit, setUnit] = useState<Unit>("px");
  const scale = unit === "arcsec" && canArcsec ? (arcsecScale as number) : 1;
  const unitLabel = unit === "arcsec" && canArcsec ? "″" : "px";

  useEffect(() => {
    if (!wrapperRef.current) return;
    const obs = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? MAX_PLOT_WIDTH;
      if (w > 0) setWidth(Math.min(MAX_PLOT_WIDTH, w));
    });
    obs.observe(wrapperRef.current);
    return () => obs.disconnect();
  }, []);

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
    const theta = Math.atan2(vxy, vxx);
    const cost = Math.cos(theta);
    const sint = Math.sin(theta);
    let rotVx = 0;
    let rotVy = 0;
    for (const p of pts) {
      const dx = p.x - mx;
      const dy = p.y - my;
      const xr = dx * cost + dy * sint;
      const yr = dy * cost - dx * sint;
      rotVx += xr * xr;
      rotVy += yr * yr;
    }
    rotVx /= pts.length;
    rotVy /= pts.length;
    const rx = Math.sqrt(Math.max(0, rotVx));
    const ry = Math.sqrt(Math.max(0, rotVy));

    const pointMax = pts.reduce(
      (m, p) => Math.max(m, Math.abs(p.x), Math.abs(p.y)),
      0,
    );
    const ellipseMax =
      Math.max(Math.abs(mx), Math.abs(my)) + 2 * Math.max(rx, ry);
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

  const domainMax = stats.maxAbs * scale;
  const xScale = d3
    .scaleLinear()
    .domain([-domainMax, domainMax])
    .range([MARGIN.left + padX, MARGIN.left + padX + side]);
  const yScale = d3
    .scaleLinear()
    .domain([-domainMax, domainMax])
    .range([MARGIN.top + side, MARGIN.top]);

  const gridColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)";
  const axisColor = isDark ? "rgba(255,255,255,0.6)" : "rgba(0,0,0,0.6)";
  const textColor = isDark ? "rgba(255,255,255,0.87)" : "rgba(0,0,0,0.87)";
  const xTicks = xScale.ticks(5);
  const yTicks = yScale.ticks(5);

  const tickDigits = unit === "arcsec" && canArcsec ? 2 : 1;
  const formatTick = (v: number) => v.toFixed(tickDigits);

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
      <Tooltip
        title="2-D scatter of guide-star positions with 1σ / 2σ dispersion ellipses."
        arrow
        placement="top"
      >
        <Typography variant="subtitle2" sx={{ cursor: "help" }}>
          {title}
        </Typography>
      </Tooltip>
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

  const centroidSvg = stats.centroid
    ? {
        x: xScale(stats.centroid.x * scale),
        y: yScale(stats.centroid.y * scale),
      }
    : null;

  const pxPerUnit = side / (2 * domainMax);
  const ellipseDeg = stats.ellipse
    ? (-stats.ellipse.theta * 180) / Math.PI
    : 0;

  const fmtVal = (v: number) => (v * scale).toFixed(unit === "arcsec" && canArcsec ? 3 : 3);

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
              {stats.pts.map((p, i) => (
                <circle
                  key={i}
                  cx={xScale(p.x * scale)}
                  cy={yScale(p.y * scale)}
                  r={1.5}
                  fill={RIG_BLUE}
                  opacity={0.4}
                />
              ))}
              {stats.ellipse && centroidSvg && (
                <g
                  transform={`rotate(${ellipseDeg} ${centroidSvg.x} ${centroidSvg.y})`}
                >
                  <ellipse
                    cx={centroidSvg.x}
                    cy={centroidSvg.y}
                    rx={stats.ellipse.rx * scale * pxPerUnit * 2}
                    ry={stats.ellipse.ry * scale * pxPerUnit * 2}
                    fill="none"
                    stroke={ELLIPSE_COLOR}
                    strokeWidth={1.5}
                    strokeDasharray="5 4"
                  />
                  <ellipse
                    cx={centroidSvg.x}
                    cy={centroidSvg.y}
                    rx={stats.ellipse.rx * scale * pxPerUnit}
                    ry={stats.ellipse.ry * scale * pxPerUnit}
                    fill="none"
                    stroke={ELLIPSE_COLOR}
                    strokeWidth={2}
                  />
                </g>
              )}
              {stats.ellipse && (
                <g>
                  <line
                    x1={MARGIN.left + padX + 8}
                    x2={MARGIN.left + padX + 24}
                    y1={MARGIN.top + 14}
                    y2={MARGIN.top + 14}
                    stroke={ELLIPSE_COLOR}
                    strokeWidth={2}
                  />
                  <text
                    x={MARGIN.left + padX + 28}
                    y={MARGIN.top + 17}
                    fill={textColor}
                    fontSize={10}
                  >
                    1σ
                  </text>
                  <line
                    x1={MARGIN.left + padX + 8}
                    x2={MARGIN.left + padX + 24}
                    y1={MARGIN.top + 30}
                    y2={MARGIN.top + 30}
                    stroke={ELLIPSE_COLOR}
                    strokeWidth={1.5}
                    strokeDasharray="5 4"
                  />
                  <text
                    x={MARGIN.left + padX + 28}
                    y={MARGIN.top + 33}
                    fill={textColor}
                    fontSize={10}
                  >
                    2σ
                  </text>
                </g>
              )}
              {centroidSvg && (
                <g>
                  <circle
                    cx={centroidSvg.x}
                    cy={centroidSvg.y}
                    r={3}
                    fill={ELLIPSE_COLOR}
                  />
                  <circle
                    cx={centroidSvg.x}
                    cy={centroidSvg.y}
                    r={5}
                    fill="none"
                    stroke={ELLIPSE_COLOR}
                    strokeWidth={1.25}
                  />
                </g>
              )}
              {xTicks.map((t) => (
                <text
                  key={`xt-${t}`}
                  x={xScale(t)}
                  y={MARGIN.top + side + 14}
                  fill={textColor}
                  fontSize={9}
                  textAnchor="middle"
                >
                  {formatTick(t)}
                </text>
              ))}
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
                  {formatTick(t)}
                </text>
              ))}
              <text
                x={(MARGIN.left + padX * 2 + side) / 2}
                y={height - 4}
                fill={textColor}
                fontSize={10}
                textAnchor="middle"
              >
                {`dx (${unitLabel})`}
              </text>
              <text
                transform={`translate(12, ${MARGIN.top + side / 2}) rotate(-90)`}
                fill={textColor}
                fontSize={10}
                textAnchor="middle"
              >
                {`dy (${unitLabel})`}
              </text>
            </svg>
            {canArcsec && (
              <ToggleButtonGroup
                value={unit}
                exclusive
                onChange={(_, v) => { if (v) setUnit(v); }}
                size="small"
                sx={{ mt: 0.5 }}
              >
                <ToggleButton value="px" sx={{ px: 1.5, py: 0.25, fontSize: 11, textTransform: "none" }}>
                  px
                </ToggleButton>
                <ToggleButton value="arcsec" sx={{ px: 1.5, py: 0.25, fontSize: 11 }}>
                  {"″"}
                </ToggleButton>
              </ToggleButtonGroup>
            )}
          </Box>
          <Box sx={{ flex: 1, minWidth: 180 }}>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              Dispersion shape
            </Typography>
            <Typography variant="body2" sx={{ display: "block", fontVariantNumeric: "tabular-nums" }}>
              Centroid: dx {fmtVal(stats.centroid?.x ?? 0)}, dy{" "}
              {fmtVal(stats.centroid?.y ?? 0)} {unitLabel}
            </Typography>
            {stats.ellipse && (
              <>
                <Typography
                  variant="body2"
                  sx={{ display: "block", fontVariantNumeric: "tabular-nums", mt: 0.5 }}
                >
                  {"1σ axes: "}
                  {fmtVal(stats.ellipse.rx)}
                  {" × "}
                  {fmtVal(stats.ellipse.ry)}
                  {` ${unitLabel}`}
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
