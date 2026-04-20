/**
 * FOV Simulator annotation overlay — circles + labels around catalog
 * DSOs that fall within the preview image.
 *
 * The overlay is rendered in **CSS-pixel** coordinates (no SVG
 * viewBox scaling). This matters because the overlay lives inside the
 * FovSimulator's pan group, whose CSS width grows with ``gridN`` —
 * first 3×size, then 5×size once the outer tile ring preloads. With a
 * fixed ``viewBox`` the user-visible font sizes and strokes would jump
 * by gridN/prev-gridN (e.g. 67%) at the promotion. Sizing everything
 * in CSS px instead keeps the visual scale constant; only the pan
 * group's own ``scale(zoom)`` transform shrinks things proportionally
 * when the user zooms out.
 *
 * ``pointer-events: none`` on the root so drags still land on the
 * rectangle underneath. Individual clickable <g>s override with
 * ``auto`` so label/circle clicks reach the popover handler.
 */
import { useMemo } from "react";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";
import type { NearbyDsoItem } from "@/api/planner";
import {
  isLabelOnly,
  passesThreshold,
  projectRaDecToTilePixel,
  radiusPxForArcmin,
} from "@/lib/dsoAnnotations";

interface Props {
  /** Nearby companion DSOs fetched from /api/planner/dsos/in-region. */
  items: NearbyDsoItem[];
  /** Primary target — always rendered regardless of threshold, with a
   *  slightly thicker stroke. Passed separately because it isn't in
   *  ``items`` (the fetch excludes it). */
  primary: {
    id: number;
    primary_designation: string;
    ra_deg: number;
    dec_deg: number;
    maj_axis_arcmin: number | null;
  };
  /** Image centre RA/Dec — same values the simulator feeds the tiles. */
  centerRaDeg: number;
  centerDecDeg: number;
  /** Angular extent of a single tile (degrees). Same value passed to
   *  ``computeTiles`` + ``ThumbnailCell`` in the simulator — annotation
   *  projection picks the right tile and matches its gnomonic image. */
  tileExtentDeg: number;
  /** Number of tiles per row/column in the current grid (1, 3, or 5). */
  gridN: number;
  /** CSS width/height of the overlay (square). Must match the pan
   *  group's unscaled size so projected positions land on the right
   *  sky point regardless of zoom. */
  sizePx: number;
  /** Minimum angular major axis (arcmin) below which non-primary
   *  objects are hidden. ``0`` shows everything that has a size. */
  thresholdArcmin: number;
  onAnnotationClick?: (item: NearbyDsoItem, anchorEl: Element) => void;
}

// Constant CSS-px typography + stroke widths. Labels and strokes feel
// the same whether the simulator is rendering a 3×3 or a 5×5 grid.
const FONT_PRIMARY = 14;
const FONT_COMPANION = 12;
const STROKE_PRIMARY = 2.0;
const STROKE_COMPANION = 1.25;
const TEXT_STROKE = 2.5;
const MIN_CIRCLE_RADIUS = 4;
const FALLBACK_POINT_RADIUS = 4;
const LABEL_GAP = 3;
const LABEL_EDGE_PAD = 20;

export default function DsoAnnotationOverlay({
  items,
  primary,
  centerRaDeg,
  centerDecDeg,
  tileExtentDeg,
  gridN,
  sizePx,
  thresholdArcmin,
  onAnnotationClick,
}: Props) {
  // ``halfGrid`` and ``tilePx`` feed both the projection and the
  // label-sizing helpers. Sizing from the per-tile extent (rather than
  // the grid-wide extent used previously) makes circle radii and the
  // ``too-large-to-circle`` threshold track what the user sees inside
  // a single tile — same fraction-of-screen regardless of whether the
  // outer grid is 1, 3, or 5 tiles wide.
  const halfGrid = (gridN - 1) / 2;
  const tilePx = sizePx / gridN;
  const itemById = useMemo(() => {
    const m = new Map<number, NearbyDsoItem>();
    for (const it of items) m.set(it.id, it);
    return m;
  }, [items]);

  const annotations = useMemo(() => {
    type Annotation = {
      id: number;
      designation: string;
      raDeg: number;
      decDeg: number;
      majorArcmin: number | null;
      isPrimary: boolean;
    };
    const rows: Annotation[] = [
      {
        id: primary.id,
        designation: primary.primary_designation,
        raDeg: primary.ra_deg,
        decDeg: primary.dec_deg,
        majorArcmin: primary.maj_axis_arcmin,
        isPrimary: true,
      },
      ...items.map((it) => ({
        id: it.id,
        designation: it.primary_designation,
        raDeg: it.ra_deg,
        decDeg: it.dec_deg,
        majorArcmin: it.maj_axis_arcmin,
        isPrimary: false,
      })),
    ];
    return rows.filter(
      (a) => a.isPrimary || passesThreshold(a.majorArcmin, thresholdArcmin),
    );
  }, [items, primary, thresholdArcmin]);

  return (
    <svg
      width={sizePx}
      height={sizePx}
      style={{
        position: "absolute",
        inset: 0,
        width: sizePx,
        height: sizePx,
        pointerEvents: "none",
        overflow: "visible",
      }}
    >
      {annotations.map((a) => {
        const { cx, cy } = projectRaDecToTilePixel(
          a.raDeg,
          a.decDeg,
          centerRaDeg,
          centerDecDeg,
          tileExtentDeg,
          halfGrid,
          tilePx,
        );
        const labelOnly = isLabelOnly(a.majorArcmin, tileExtentDeg);
        const strokeW = a.isPrimary ? STROKE_PRIMARY : STROKE_COMPANION;
        const color = a.isPrimary ? RIG_ORANGE : RIG_BLUE;
        const fontSize = a.isPrimary ? FONT_PRIMARY : FONT_COMPANION;
        const key = `${a.id}-${a.isPrimary ? "p" : "c"}`;

        const clickable = !a.isPrimary && onAnnotationClick != null;
        const interactiveProps = clickable
          ? {
              style: { pointerEvents: "auto" as const, cursor: "pointer" },
              onPointerDown: (e: React.PointerEvent<SVGGElement>) => {
                e.stopPropagation();
                const nearby = itemById.get(a.id);
                if (nearby) onAnnotationClick(nearby, e.currentTarget);
              },
            }
          : {};

        if (labelOnly) {
          // Clip the label to the edge so a just-offscreen giant
          // (e.g., Andromeda with a tiny rig) still shows by name.
          const clampedX = Math.max(
            LABEL_EDGE_PAD,
            Math.min(sizePx - LABEL_EDGE_PAD, cx),
          );
          const clampedY = Math.max(
            LABEL_EDGE_PAD,
            Math.min(sizePx - 8, cy),
          );
          return (
            <g key={key} {...interactiveProps}>
              <text
                x={clampedX}
                y={clampedY}
                fill={color}
                fontSize={fontSize}
                fontWeight={a.isPrimary ? 700 : 500}
                textAnchor="middle"
                stroke="#000000"
                strokeWidth={TEXT_STROKE}
                paintOrder="stroke"
              >
                {a.designation}
              </text>
            </g>
          );
        }

        const r =
          a.majorArcmin != null
            ? Math.max(
                MIN_CIRCLE_RADIUS,
                radiusPxForArcmin(a.majorArcmin, tilePx, tileExtentDeg),
              )
            : FALLBACK_POINT_RADIUS;
        return (
          <g key={key} {...interactiveProps}>
            {/* ``fill="transparent"`` (rather than "none") so the
                entire enclosed disc is a pointer-event target, not
                just the stroke. Matters for small companions whose
                1 px stroke is otherwise fiddly to click. */}
            <circle
              cx={cx}
              cy={cy}
              r={r}
              fill="transparent"
              stroke={color}
              strokeWidth={strokeW}
              opacity={0.85}
            />
            <text
              x={cx + r + LABEL_GAP}
              y={cy + fontSize * 0.35}
              fill={color}
              fontSize={fontSize}
              fontWeight={a.isPrimary ? 700 : 500}
              stroke="#000000"
              strokeWidth={TEXT_STROKE}
              paintOrder="stroke"
            >
              {a.designation}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
