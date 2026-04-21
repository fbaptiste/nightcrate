/**
 * FOV Simulator annotation overlay — circles + labels around catalog
 * DSOs that fall within the preview image.
 *
 * v0.18.0 / Pass C: every cell in the composite shares a single
 * region tangent, so annotations project via one gnomonic transform
 * (``projectRaDecInRegion``). The per-tile nearest-tangent dance from
 * v0.17.0 is no longer needed.
 *
 * Rendered in **CSS-pixel** (really: composite source-pixel)
 * coordinates with no SVG viewBox. The parent pan group's
 * ``scale(zoom)`` transform shrinks everything proportionally when the
 * user zooms out.
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
  projectRaDecInRegion,
  radiusPxForArcmin,
} from "@/lib/dsoAnnotations";

interface Props {
  items: NearbyDsoItem[];
  primary: {
    id: number;
    primary_designation: string;
    ra_deg: number;
    dec_deg: number;
    maj_axis_arcmin: number | null;
  };
  /** HEALPix region tangent point — the shared gnomonic centre for
   *  every cell + annotation in the composite. */
  tangentRaDeg: number;
  tangentDecDeg: number;
  /** Cell spec from the grid layout — feeds the pixel scale. */
  cellSizeDeg: number;
  cellPxSize: number;
  /** Composite dimensions (source pixels). The SVG matches this so
   *  the pan-group ``scale(zoom)`` transform carries annotations with
   *  the image. */
  compositePxWidth: number;
  compositePxHeight: number;
  /** Where the simulator's view centre (the DSO's RA/Dec) lands in
   *  the composite. The projection anchors around this so the primary
   *  always sits at its visual centre regardless of cell-boundary
   *  alignment. */
  viewCenterPxX: number;
  viewCenterPxY: number;
  /** Minimum angular major axis (arcmin) below which non-primary
   *  objects are hidden. ``0`` shows everything that has a size. */
  thresholdArcmin: number;
  onAnnotationClick?: (item: NearbyDsoItem, anchorEl: Element) => void;
}

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
  tangentRaDeg,
  tangentDecDeg,
  cellSizeDeg,
  cellPxSize,
  compositePxWidth,
  compositePxHeight,
  viewCenterPxX,
  viewCenterPxY,
  thresholdArcmin,
  onAnnotationClick,
}: Props) {
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
      width={compositePxWidth}
      height={compositePxHeight}
      style={{
        position: "absolute",
        inset: 0,
        width: compositePxWidth,
        height: compositePxHeight,
        pointerEvents: "none",
        overflow: "visible",
      }}
    >
      {annotations.map((a) => {
        const { cx, cy } = projectRaDecInRegion(
          a.raDeg,
          a.decDeg,
          tangentRaDeg,
          tangentDecDeg,
          cellSizeDeg,
          cellPxSize,
          viewCenterPxX,
          viewCenterPxY,
          primary.ra_deg,
          primary.dec_deg,
        );
        const labelOnly = isLabelOnly(a.majorArcmin, cellSizeDeg);
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
          const clampedX = Math.max(
            LABEL_EDGE_PAD,
            Math.min(compositePxWidth - LABEL_EDGE_PAD, cx),
          );
          const clampedY = Math.max(
            LABEL_EDGE_PAD,
            Math.min(compositePxHeight - 8, cy),
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
                radiusPxForArcmin(a.majorArcmin, cellPxSize, cellSizeDeg),
              )
            : FALLBACK_POINT_RADIUS;
        return (
          <g key={key} {...interactiveProps}>
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
