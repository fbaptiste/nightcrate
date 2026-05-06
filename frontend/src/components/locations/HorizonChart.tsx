import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import { useTheme } from "@mui/material/styles";
import * as d3 from "d3";

import { RIG_BLUE, RIG_ORANGE, RIG_TEAL } from "@/lib/rigColors";

export interface HorizonPoint {
  azimuth_deg: number; // storage coords, [0, 360)
  altitude_deg: number;
}

export type AltitudeRange = "fit" | "0-90";
export type HorizonChartMode = "readonly" | "editable";

interface HorizonChartProps {
  points: HorizonPoint[];
  referencePoints?: HorizonPoint[] | null;
  originalPoints?: HorizonPoint[] | null;
  altitudeRange?: AltitudeRange;
  mode?: HorizonChartMode;
  showRawPoints?: boolean; // overlay measurement markers on readonly line
  width?: number;
  height?: number;
  onPointDrag?: (index: number, az: number, alt: number) => void;
  onPointDragEnd?: () => void;
  onPointAdd?: (az: number, alt: number) => void;
  onPointEditStart?: (index: number) => void;
}

const MARGIN = { top: 16, right: 16, bottom: 32, left: 40 } as const;

/** Storage azimuth [0,360) → display x [-180,+180]. N-centered. */
function toDisplayX(azimuthDeg: number): number {
  return azimuthDeg <= 180 ? azimuthDeg : azimuthDeg - 360;
}

/** Linearly interpolate altitude at `targetAz` from a storage-sorted list. */
function interpolateAltAt(sorted: HorizonPoint[], targetAz: number): number {
  const exact = sorted.find((p) => p.azimuth_deg === targetAz);
  if (exact) return exact.altitude_deg;
  let before: HorizonPoint | undefined;
  let after: HorizonPoint | undefined;
  for (const p of sorted) {
    if (p.azimuth_deg < targetAz) before = p;
    else if (p.azimuth_deg > targetAz && after === undefined) after = p;
  }
  if (before && after) {
    const span = after.azimuth_deg - before.azimuth_deg;
    const t = (targetAz - before.azimuth_deg) / span;
    return before.altitude_deg + t * (after.altitude_deg - before.altitude_deg);
  }
  if (before) return before.altitude_deg;
  if (after) return after.altitude_deg;
  return 0;
}

/** Build the display-ordered polyline with virtual edge points at ±180 (S seam).
 *  When fewer than 2 points exist, returns the implicit flat baseline at
 *  alt=0° so the chart always shows a horizon reference. */
function buildDisplayPolyline(points: HorizonPoint[]): Array<[number, number]> {
  if (points.length < 2) {
    return [
      [-180, 0],
      [180, 0],
    ];
  }
  const sorted = [...points].sort((a, b) => a.azimuth_deg - b.azimuth_deg);
  const seamAlt = interpolateAltAt(sorted, 180);
  const leftHalf = sorted
    .filter((p) => p.azimuth_deg > 180)
    .map((p) => [p.azimuth_deg - 360, p.altitude_deg] as [number, number]);
  const rightHalf = sorted
    .filter((p) => p.azimuth_deg <= 180)
    .map((p) => [p.azimuth_deg, p.altitude_deg] as [number, number]);
  return [[-180, seamAlt], ...leftHalf, ...rightHalf, [180, seamAlt]];
}

const CARDINAL_TICKS: Array<{ x: number; label: string }> = [
  { x: -180, label: "S" },
  { x: -90, label: "W" },
  { x: 0, label: "N" },
  { x: 90, label: "E" },
  { x: 180, label: "S" },
];

export default function HorizonChart({
  points,
  referencePoints = null,
  originalPoints = null,
  altitudeRange = "fit",
  mode = "readonly",
  showRawPoints = false,
  width = 960,
  height = 240,
  onPointDrag,
  onPointDragEnd,
  onPointAdd,
  onPointEditStart,
}: HorizonChartProps) {
  const theme = useTheme();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; az: number; alt: number } | null>(
    null,
  );

  const innerWidth = width - MARGIN.left - MARGIN.right;
  const innerHeight = height - MARGIN.top - MARGIN.bottom;

  // Single-pass scan across every visible layer (editable, trace reference,
  // original-comparison) so nothing is clipped by the y-axis. Using a
  // spread + Math.max/min would hit the argument-limit for huge imports.
  const [minAlt, maxAlt] = useMemo<[number, number]>(() => {
    if (altitudeRange === "0-90") return [0, 90];
    let lo = Infinity;
    let hi = -Infinity;
    const scan = (arr: HorizonPoint[] | null | undefined) => {
      if (!arr) return;
      for (const p of arr) {
        if (p.altitude_deg < lo) lo = p.altitude_deg;
        if (p.altitude_deg > hi) hi = p.altitude_deg;
      }
    };
    scan(points);
    scan(referencePoints);
    scan(originalPoints);
    if (!Number.isFinite(lo)) return [0, 45];
    return [
      Math.min(0, Math.floor(lo / 5) * 5),
      Math.max(30, Math.ceil((hi + 5) / 5) * 5),
    ];
  }, [altitudeRange, points, referencePoints, originalPoints]);

  const xScale = useMemo(
    () => d3.scaleLinear().domain([-180, 180]).range([0, innerWidth]),
    [innerWidth],
  );
  const yScale = useMemo(
    () => d3.scaleLinear().domain([minAlt, maxAlt]).range([innerHeight, 0]),
    [innerHeight, minAlt, maxAlt],
  );

  const displayPoints = useMemo(() => buildDisplayPolyline(points), [points]);
  const referenceDisplayPoints = useMemo(
    () => (referencePoints && referencePoints.length >= 2 ? buildDisplayPolyline(referencePoints) : []),
    [referencePoints],
  );
  const originalDisplayPoints = useMemo(
    () => (originalPoints && originalPoints.length >= 2 ? buildDisplayPolyline(originalPoints) : []),
    [originalPoints],
  );

  const curve = useMemo(() => d3.curveLinear, []);

  const makeLine = useCallback(
    (pts: Array<[number, number]>, c: d3.CurveFactory | d3.CurveFactoryLineOnly) =>
      d3.line<[number, number]>().curve(c).x((d) => xScale(d[0])).y((d) => yScale(d[1]))(pts) ?? "",
    [xScale, yScale],
  );

  const linePath = useMemo(() => makeLine(displayPoints, curve), [displayPoints, curve, makeLine]);
  const areaPath = useMemo(() => {
    const gen = d3
      .area<[number, number]>()
      .curve(curve)
      .x((d) => xScale(d[0]))
      .y0(yScale(minAlt))
      .y1((d) => yScale(d[1]));
    return gen(displayPoints) ?? "";
  }, [displayPoints, xScale, yScale, minAlt, curve]);

  // Reference guide: smooth Catmull-Rom (it's a shape guide, not raw data).
  const referenceLinePath = useMemo(
    () =>
      referenceDisplayPoints.length >= 2
        ? makeLine(referenceDisplayPoints, d3.curveLinear)
        : "",
    [referenceDisplayPoints, makeLine],
  );
  // Original comparison: linear, so the user sees exactly what was stored.
  const originalLinePath = useMemo(
    () =>
      originalDisplayPoints.length >= 2 ? makeLine(originalDisplayPoints, d3.curveLinear) : "",
    [originalDisplayPoints, makeLine],
  );

  const azTicks = useMemo(
    () => [-180, -150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150, 180],
    [],
  );
  const altTicks = useMemo(() => yScale.ticks(Math.min(9, Math.round(innerHeight / 30))), [
    yScale,
    innerHeight,
  ]);

  const gridColor = theme.palette.divider;
  const cardinalColor = theme.palette.text.secondary;
  const labelColor = theme.palette.text.primary;

  const dragIndexRef = useRef<number | null>(null);
  const dragMovedRef = useRef<boolean>(false);

  // Small tolerance band around the chart so a click just outside the
  // plotted area (e.g. a hair below the 0° baseline) still registers.
  const CLICK_SLOP = 15;

  const localFromEvent = useCallback(
    (clientX: number, clientY: number): { x: number; y: number; az: number; alt: number } | null => {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return null;
      const localX = clientX - rect.left - MARGIN.left;
      const localY = clientY - rect.top - MARGIN.top;
      if (
        localX < 0 ||
        localX > innerWidth ||
        localY < -CLICK_SLOP ||
        localY > innerHeight + CLICK_SLOP
      ) {
        return null;
      }
      const displayAz = xScale.invert(localX);
      const storageAz = displayAz < 0 ? displayAz + 360 : displayAz;
      const alt = yScale.invert(Math.max(0, Math.min(innerHeight, localY)));
      return { x: localX, y: localY, az: storageAz, alt };
    },
    [innerHeight, innerWidth, xScale, yScale],
  );

  const onOverlayMouseMove = (e: React.MouseEvent<SVGRectElement>) => {
    const pos = localFromEvent(e.clientX, e.clientY);
    setHover(pos);
  };

  const onOverlayMouseLeave = () => setHover(null);

  const onOverlayDoubleClick = (e: React.MouseEvent<SVGRectElement>) => {
    if (mode !== "editable" || !onPointAdd) return;
    const pos = localFromEvent(e.clientX, e.clientY);
    if (!pos) return;
    const az = Math.round(pos.az * 10) / 10;
    const clampedAlt = Math.max(minAlt, Math.min(maxAlt, pos.alt));
    const alt = Math.round(clampedAlt * 10) / 10;
    onPointAdd(((az % 360) + 360) % 360, Math.max(-5, Math.min(90, alt)));
  };

  const onPointMouseDown = (index: number) => (e: React.MouseEvent<SVGCircleElement>) => {
    if (mode !== "editable") return;
    // Only start a drag on left button; let right-click fall through to
    // the contextmenu handler below.
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    dragIndexRef.current = index;
    dragMovedRef.current = false;
  };

  const onPointContextMenu = (index: number) => (e: React.MouseEvent<SVGCircleElement>) => {
    if (mode !== "editable" || !onPointEditStart) return;
    e.preventDefault();
    e.stopPropagation();
    onPointEditStart(index);
  };

  useEffect(() => {
    if (mode !== "editable") return;
    const handleMove = (e: MouseEvent) => {
      const idx = dragIndexRef.current;
      if (idx === null || !onPointDrag) return;
      const pos = localFromEvent(e.clientX, e.clientY);
      if (!pos) return;
      dragMovedRef.current = true;
      const az = Math.round(pos.az * 10) / 10;
      const alt = Math.round(pos.alt * 10) / 10;
      onPointDrag(idx, ((az % 360) + 360) % 360, Math.max(-5, Math.min(90, alt)));
    };
    const handleUp = () => {
      if (dragIndexRef.current !== null && dragMovedRef.current && onPointDragEnd) {
        onPointDragEnd();
      }
      dragIndexRef.current = null;
      dragMovedRef.current = false;
    };
    const handleTouchMove = (e: TouchEvent) => {
      const idx = dragIndexRef.current;
      if (idx === null || !onPointDrag || e.touches.length !== 1) return;
      e.preventDefault();
      const pos = localFromEvent(e.touches[0].clientX, e.touches[0].clientY);
      if (!pos) return;
      dragMovedRef.current = true;
      const az = Math.round(pos.az * 10) / 10;
      const alt = Math.round(pos.alt * 10) / 10;
      onPointDrag(idx, ((az % 360) + 360) % 360, Math.max(-5, Math.min(90, alt)));
    };
    const handleTouchEnd = () => {
      if (dragIndexRef.current !== null && dragMovedRef.current && onPointDragEnd) {
        onPointDragEnd();
      }
      dragIndexRef.current = null;
      dragMovedRef.current = false;
    };
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    window.addEventListener("touchmove", handleTouchMove, { passive: false });
    window.addEventListener("touchend", handleTouchEnd);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", handleTouchEnd);
    };
  }, [mode, onPointDrag, onPointDragEnd, localFromEvent]);

  return (
    <Box sx={{ position: "relative", width, height }}>
      <svg
        ref={svgRef}
        width={width}
        height={height}
        style={{ display: "block", overflow: "visible" }}
        role="img"
        aria-label="Horizon panorama chart"
      >
        <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
          {/* Minor gridlines */}
          {azTicks.map((t) => (
            <line
              key={`vg-${t}`}
              x1={xScale(t)}
              x2={xScale(t)}
              y1={0}
              y2={innerHeight}
              stroke={gridColor}
              strokeWidth={1}
              opacity={0.4}
            />
          ))}
          {altTicks.map((t) => (
            <line
              key={`hg-${t}`}
              x1={0}
              x2={innerWidth}
              y1={yScale(t)}
              y2={yScale(t)}
              stroke={gridColor}
              strokeWidth={1}
              opacity={0.4}
            />
          ))}

          {/* Cardinal ticks — slightly bolder */}
          {CARDINAL_TICKS.map((c, i) => (
            <line
              key={`ct-${i}`}
              x1={xScale(c.x)}
              x2={xScale(c.x)}
              y1={0}
              y2={innerHeight}
              stroke={cardinalColor}
              strokeWidth={1}
              opacity={0.75}
            />
          ))}

          {/* Original-comparison overlay — dotted blue, sits beneath the
              trace reference so both are visible when toggled together */}
          {originalLinePath && (
            <path
              d={originalLinePath}
              fill="none"
              stroke={RIG_BLUE}
              strokeWidth={2}
              strokeOpacity={0.6}
              strokeDasharray="1 4"
              strokeLinejoin="round"
              strokeLinecap="round"
              pointerEvents="none"
            />
          )}

          {/* Trace reference overlay — dashed orange "shape guide" */}
          {referenceLinePath && (
            <path
              d={referenceLinePath}
              fill="none"
              stroke={RIG_ORANGE}
              strokeWidth={2}
              strokeOpacity={0.6}
              strokeDasharray="5 4"
              strokeLinejoin="round"
              strokeLinecap="round"
              pointerEvents="none"
            />
          )}

          {/* Obstruction fill — only when the user has defined a horizon */}
          {points.length >= 2 && (
            <path d={areaPath} fill={RIG_TEAL} fillOpacity={0.25} stroke="none" />
          )}

          {/* Horizon line — solid for user-defined, dashed for the implicit 0° baseline */}
          <path
            d={linePath}
            fill="none"
            stroke={RIG_ORANGE}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeDasharray={points.length < 2 ? "6 4" : undefined}
            strokeOpacity={points.length < 2 ? 0.55 : 1}
          />

          {/* Hover crosshair */}
          {hover && (
            <>
              <line
                x1={hover.x}
                x2={hover.x}
                y1={0}
                y2={innerHeight}
                stroke={cardinalColor}
                strokeWidth={1}
                strokeDasharray="3 3"
                opacity={0.6}
                pointerEvents="none"
              />
              <line
                x1={0}
                x2={innerWidth}
                y1={hover.y}
                y2={hover.y}
                stroke={cardinalColor}
                strokeWidth={1}
                strokeDasharray="3 3"
                opacity={0.6}
                pointerEvents="none"
              />
            </>
          )}

          {/* Mouse-capture overlay (sits under the point markers).
              Extended by CLICK_SLOP below so clicks just beneath the 0°
              baseline still register. */}
          <rect
            x={0}
            y={-CLICK_SLOP}
            width={innerWidth}
            height={innerHeight + 2 * CLICK_SLOP}
            fill="transparent"
            style={{ cursor: mode === "editable" ? "crosshair" : "default" }}
            onMouseMove={onOverlayMouseMove}
            onMouseLeave={onOverlayMouseLeave}
            onTouchStart={(e) => { if (e.touches.length === 1) setHover(localFromEvent(e.touches[0].clientX, e.touches[0].clientY)); }}
            onTouchMove={(e) => { if (e.touches.length === 1) { e.preventDefault(); setHover(localFromEvent(e.touches[0].clientX, e.touches[0].clientY)); } }}
            onTouchEnd={() => setHover(null)}
            onDoubleClick={onOverlayDoubleClick}
            onContextMenu={(e) => {
              if (mode === "editable") e.preventDefault();
            }}
          />

          {/* Point markers — always in editable mode; optional overlay in readonly */}
          {(mode === "editable" || showRawPoints) &&
            points.map((p, i) => {
              const dx = toDisplayX(p.azimuth_deg);
              return (
                <circle
                  key={`pt-${i}`}
                  cx={xScale(dx)}
                  cy={yScale(p.altitude_deg)}
                  r={mode === "editable" ? 5 : 3}
                  fill={RIG_ORANGE}
                  stroke={theme.palette.background.paper}
                  strokeWidth={1.5}
                  style={{ cursor: mode === "editable" ? "grab" : "default" }}
                  onMouseDown={mode === "editable" ? onPointMouseDown(i) : undefined}
                  onTouchStart={mode === "editable" ? (e) => { e.stopPropagation(); e.preventDefault(); dragIndexRef.current = i; dragMovedRef.current = false; } : undefined}
                  onContextMenu={mode === "editable" ? onPointContextMenu(i) : undefined}
                />
              );
            })}

          {/* Axis labels */}
          {altTicks.map((t) => (
            <text
              key={`ay-${t}`}
              x={-8}
              y={yScale(t)}
              fontSize={10}
              fill={labelColor}
              textAnchor="end"
              dominantBaseline="middle"
            >
              {t}&deg;
            </text>
          ))}
          {CARDINAL_TICKS.map((c, i) => (
            <text
              key={`cl-${i}`}
              x={xScale(c.x)}
              y={innerHeight + 14}
              fontSize={12}
              fontWeight={600}
              fill={labelColor}
              textAnchor="middle"
            >
              {c.label}
            </text>
          ))}
          {[-135, -45, 45, 135].map((x) => (
            <text
              key={`sl-${x}`}
              x={xScale(x)}
              y={innerHeight + 14}
              fontSize={10}
              fill={cardinalColor}
              textAnchor="middle"
            >
              {x < 0 ? x + 360 : x}&deg;
            </text>
          ))}
        </g>
      </svg>

      {/* Hover readout badge */}
      {hover && (
        <Box
          sx={{
            position: "absolute",
            left: hover.x + MARGIN.left + 12,
            top: hover.y + MARGIN.top + 12,
            px: 1,
            py: 0.5,
            bgcolor: "background.paper",
            border: 1,
            borderColor: "divider",
            borderRadius: 1,
            fontFamily: "monospace",
            fontSize: 12,
            pointerEvents: "none",
            whiteSpace: "nowrap",
            boxShadow: 1,
          }}
        >
          az {hover.az.toFixed(1)}&deg; &middot; alt {hover.alt.toFixed(1)}&deg;
        </Box>
      )}

    </Box>
  );
}
