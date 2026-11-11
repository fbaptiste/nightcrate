import { useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import type { GalleryMark, GallerySolveMarks } from "@/api/gallery";
import { projectSolveImageUrl } from "@/api/projectSolve";
import MatchChips from "./MatchChips";

type SolveVariant = "full" | "thumb_lg" | "thumb_md" | "thumb_sm";

interface Props {
  projectId: number;
  solve: GallerySolveMarks;
  variant: SolveVariant;
  ws: string;
  alt: string;
  inset?: boolean;
  onUnavailable: () => void;
  matchMainTarget?: boolean;
  matchInImage?: boolean;
  compactChips?: boolean;
}

interface Size {
  width: number;
  height: number;
}

interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface ScreenMark {
  mark: GalleryMark;
  cx: number;
  cy: number;
  rx: number;
  ry: number;
  bounds: Rect;
}

interface LabelLayout extends Rect {
  mark: GalleryMark;
  baseline: number;
}

function markOrder(a: GalleryMark, b: GalleryMark): number {
  return Number(b.main_target) - Number(a.main_target) ||
    a.designation.localeCompare(b.designation);
}

function intersects(a: Rect, b: Rect): boolean {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

function inside(rect: Rect, bounds: Rect): boolean {
  return (
    rect.left >= bounds.left &&
    rect.right <= bounds.right &&
    rect.top >= bounds.top &&
    rect.bottom <= bounds.bottom
  );
}

function labelRect(left: number, top: number, width: number, mark: GalleryMark): LabelLayout {
  return {
    mark,
    left,
    top,
    right: left + width,
    bottom: top + 16,
    baseline: top + 12,
  };
}

function placeLabels(
  marks: ScreenMark[],
  insetDsoId: number | null,
  imageBounds: Rect,
  showLabels: boolean,
): LabelLayout[] {
  if (!showLabels) return [];
  const placed: LabelLayout[] = [];
  const padding = 2;

  for (const screenMark of marks) {
    const { mark, cx, cy, rx } = screenMark;
    if (mark.dso_id === insetDsoId) continue;
    const width = Math.min(
      Math.max(36, mark.designation.length * 8),
      Math.max(0, imageBounds.right - imageBounds.left - padding * 2),
    );
    const top = Math.min(
      imageBounds.bottom - 16 - padding,
      Math.max(imageBounds.top + padding, cy - 8),
    );
    const right = labelRect(cx + rx + 6, top, width, mark);
    const left = labelRect(cx - rx - 6 - width, top, width, mark);
    const sideCandidates = [right, left].filter((candidate) =>
      inside(candidate, imageBounds),
    );
    const side = sideCandidates.find(
      (candidate) => !placed.some((earlier) => intersects(candidate, earlier)),
    );
    if (side) {
      placed.push(side);
      continue;
    }

    const baseLeft = Math.min(
      imageBounds.right - width - padding,
      Math.max(imageBounds.left + padding, right.left),
    );
    const base = labelRect(baseLeft, top, width, mark);
    const collisions = placed.filter((earlier) => intersects(base, earlier));
    const belowTop = collisions.length
      ? Math.max(...collisions.map((earlier) => earlier.bottom)) + 2
      : top;
    const below = labelRect(baseLeft, belowTop, width, mark);
    if (
      inside(below, imageBounds) &&
      !placed.some((earlier) => intersects(below, earlier))
    ) {
      placed.push(below);
    }
  }
  return placed;
}

export default function SolveMarkedImage({
  projectId,
  solve,
  variant,
  ws,
  alt,
  inset = true,
  onUnavailable,
  matchMainTarget = false,
  matchInImage = false,
  compactChips = false,
}: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });

  useEffect(() => {
    const root = rootRef.current;
    if (!root || near) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin: "400px" },
    );
    observer.observe(root);
    return () => observer.disconnect();
  }, [near]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const measure = () => {
      const bounds = root.getBoundingClientRect();
      setSize({ width: bounds.width, height: bounds.height });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    return () => observer.disconnect();
  }, []);

  const scale =
    size.width > 0 && size.height > 0
      ? Math.min(size.width / solve.width, size.height / solve.height)
      : 0;
  const imageWidth = solve.width * scale;
  const imageHeight = solve.height * scale;
  const offsetX = (size.width - imageWidth) / 2;
  const offsetY = (size.height - imageHeight) / 2;
  const imageBounds = useMemo<Rect>(
    () => ({
      left: offsetX,
      top: offsetY,
      right: offsetX + imageWidth,
      bottom: offsetY + imageHeight,
    }),
    [imageHeight, imageWidth, offsetX, offsetY],
  );
  const orderedMarks = useMemo(() => [...solve.marks].sort(markOrder), [solve.marks]);
  const screenMarks = useMemo<ScreenMark[]>(
    () =>
      orderedMarks.map((mark) => {
        const ownMajor = mark.semi_major_px ?? 0;
        const ownMinor = mark.semi_minor_px ?? ownMajor;
        const rx = Math.max(ownMajor * 1.3 * scale, 9);
        const ry = Math.max(ownMinor * 1.3 * scale, 9);
        const cx = offsetX + mark.pixel_x * scale;
        const cy = offsetY + mark.pixel_y * scale;
        const radius = Math.max(rx, ry);
        return {
          mark,
          cx,
          cy,
          rx,
          ry,
          bounds: {
            left: cx - radius,
            top: cy - radius,
            right: cx + radius,
            bottom: cy + radius,
          },
        };
      }),
    [offsetX, offsetY, orderedMarks, scale],
  );
  const insetScreenMark = useMemo(() => {
    if (!inset || scale <= 0) return null;
    return screenMarks.find(
      ({ mark }) => (mark.semi_major_px ?? 0) * scale < 8,
    ) ?? null;
  }, [inset, scale, screenMarks]);
  const showLabels = size.width >= 240;
  const labels = useMemo(
    () =>
      placeLabels(
        screenMarks,
        insetScreenMark?.mark.dso_id ?? null,
        imageBounds,
        showLabels,
      ),
    [imageBounds, insetScreenMark?.mark.dso_id, screenMarks, showLabels],
  );

  const diameter = Math.max(
    0,
    Math.min(220, imageHeight * 0.46, imageWidth - 16),
  );
  const topLeft = insetScreenMark
    ? Math.hypot(
        insetScreenMark.cx - imageBounds.left,
        insetScreenMark.cy - imageBounds.top,
      ) >
      Math.hypot(
        imageBounds.right - insetScreenMark.cx,
        imageBounds.bottom - insetScreenMark.cy,
      )
    : true;
  const insetLeft = topLeft
    ? imageBounds.left + 8
    : imageBounds.right - 8 - diameter;
  const insetTop = topLeft
    ? imageBounds.top + 8
    : imageBounds.bottom - 8 - diameter;
  const insetBounds: Rect | null = insetScreenMark && diameter > 0
    ? {
        left: insetLeft,
        top: insetTop,
        right: insetLeft + diameter,
        bottom: insetTop + diameter,
      }
    : null;
  const insetCenterX = insetLeft + diameter / 2;
  const insetCenterY = insetTop + diameter / 2;
  const insetScale =
    insetScreenMark && insetScreenMark.mark.inset_radius_px > 0
      ? diameter / (2 * insetScreenMark.mark.inset_radius_px)
      : 0;
  const magnification = scale > 0 ? Math.max(1, Math.round(insetScale / scale)) : 1;
  const insetText = insetScreenMark
    ? `${insetScreenMark.mark.designation} enlarged ×${magnification}`
    : "";
  const insetLabelWidth = Math.min(insetText.length * 8, Math.max(0, imageWidth - 4));
  let insetLabelBounds: Rect | null = null;
  if (insetBounds && showLabels) {
    const preferredLeft = topLeft
      ? insetBounds.left
      : insetBounds.right - insetLabelWidth;
    const left = Math.min(
      imageBounds.right - insetLabelWidth - 2,
      Math.max(imageBounds.left + 2, preferredLeft),
    );
    const preferredTop = topLeft ? insetBounds.bottom + 6 : insetBounds.top - 22;
    const top = Math.min(
      imageBounds.bottom - 16 - 2,
      Math.max(imageBounds.top + 2, preferredTop),
    );
    insetLabelBounds = { left, top, right: left + insetLabelWidth, bottom: top + 16 };
  }

  const contentBounds: Rect[] = [
    ...screenMarks.map((mark) => mark.bounds),
    ...labels,
    ...(insetBounds ? [insetBounds] : []),
    ...(insetLabelBounds ? [insetLabelBounds] : []),
  ];
  const chipOffset = compactChips ? 6 : 8;
  const chipCount = Number(matchMainTarget) + Number(matchInImage);
  const chipWidth = compactChips
    ? chipCount * 24 + Math.max(0, chipCount - 1) * 5
    : (matchMainTarget ? 104 : 0) +
      (matchInImage ? 190 : 0) +
      Math.max(0, chipCount - 1) * 5;
  const bottomChipBounds: Rect = {
    left: chipOffset,
    top: size.height - chipOffset - 24,
    right: Math.min(size.width - chipOffset, chipOffset + chipWidth),
    bottom: size.height - chipOffset,
  };
  const topChipBounds: Rect = {
    left: chipOffset,
    top: chipOffset,
    right: Math.min(size.width - chipOffset, chipOffset + chipWidth),
    bottom: chipOffset + 24,
  };
  const bottomOccupied = contentBounds.some((bounds) =>
    intersects(bounds, bottomChipBounds),
  );
  const topOccupied = contentBounds.some((bounds) => intersects(bounds, topChipBounds));
  const chipsAtTop = chipCount > 0 && bottomOccupied && !topOccupied;

  const leaderDx = insetScreenMark ? insetScreenMark.cx - insetCenterX : 0;
  const leaderDy = insetScreenMark ? insetScreenMark.cy - insetCenterY : 0;
  const leaderDistance = Math.hypot(leaderDx, leaderDy) || 1;
  const leaderX = leaderDx / leaderDistance;
  const leaderY = leaderDy / leaderDistance;
  const mainRingRadius = insetScreenMark
    ? Math.max(insetScreenMark.rx, insetScreenMark.ry)
    : 9;
  const src = projectSolveImageUrl(projectId, variant, solve.solve_id, ws);
  const fullSrc = projectSolveImageUrl(projectId, "full", solve.solve_id, ws);

  return (
    <Box
      ref={rootRef}
      sx={{
        position: "relative",
        display: "block",
        alignSelf: "stretch",
        justifySelf: "stretch",
        width: "100%",
        height: "100%",
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
      }}
    >
      {near && (
        <Box
          component="img"
          src={src}
          alt={alt}
          onLoad={() => setLoaded(true)}
          onError={onUnavailable}
          sx={{
            display: "block",
            width: "100%",
            height: "100%",
            minWidth: 0,
            minHeight: 0,
            maxWidth: "100%",
            maxHeight: "100%",
            objectFit: "contain",
          }}
        />
      )}
      {loaded && scale > 0 && (
        <Box
          component="svg"
          viewBox={`0 0 ${solve.width} ${solve.height}`}
          preserveAspectRatio="xMidYMid meet"
          aria-hidden
          sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
        >
          {orderedMarks.map((mark) => {
            const ownMajor = mark.semi_major_px ?? 0;
            const ownMinor = mark.semi_minor_px ?? ownMajor;
            const ringMajor = Math.max(ownMajor * 1.3, 9 / scale);
            const ringMinor = Math.max(ownMinor * 1.3, 9 / scale);
            return (
              <g key={mark.dso_id}>
                <ellipse
                  cx={mark.pixel_x}
                  cy={mark.pixel_y}
                  rx={ringMajor}
                  ry={ringMinor}
                  transform={`rotate(${mark.angle_deg ?? 0} ${mark.pixel_x} ${mark.pixel_y})`}
                  fill="none"
                  stroke="rgba(0,0,0,0.75)"
                  strokeWidth={4}
                  vectorEffect="non-scaling-stroke"
                />
                <ellipse
                  cx={mark.pixel_x}
                  cy={mark.pixel_y}
                  rx={ringMajor}
                  ry={ringMinor}
                  transform={`rotate(${mark.angle_deg ?? 0} ${mark.pixel_x} ${mark.pixel_y})`}
                  fill="none"
                  stroke="#ed6c02"
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            );
          })}
        </Box>
      )}
      {loaded && labels.length > 0 && (
        <Box
          component="svg"
          viewBox={`0 0 ${size.width} ${size.height}`}
          preserveAspectRatio="none"
          aria-hidden
          sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
        >
          {labels.map((label) => (
            <text
              key={label.mark.dso_id}
              x={label.left}
              y={label.baseline}
              fill="#f2c27a"
              fontSize={12}
              fontWeight={600}
              style={{ paintOrder: "stroke", stroke: "rgba(0,0,0,0.9)", strokeWidth: 3 }}
            >
              {label.mark.designation}
            </text>
          ))}
        </Box>
      )}
      {loaded && insetScreenMark && insetBounds && diameter > 0 && (
        <>
          <Box
            component="svg"
            viewBox={`0 0 ${size.width} ${size.height}`}
            preserveAspectRatio="none"
            aria-hidden
            sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
          >
            <line
              x1={insetCenterX + leaderX * (diameter / 2 + 2)}
              y1={insetCenterY + leaderY * (diameter / 2 + 2)}
              x2={insetScreenMark.cx - leaderX * (mainRingRadius + 2)}
              y2={insetScreenMark.cy - leaderY * (mainRingRadius + 2)}
              stroke="#ed6c02"
              strokeWidth={1.25}
              strokeDasharray="4 3"
              vectorEffect="non-scaling-stroke"
            />
          </Box>
          <Box
            sx={{
              position: "absolute",
              zIndex: 2,
              left: insetBounds.left,
              top: insetBounds.top,
              width: diameter,
              height: diameter,
              overflow: "hidden",
              borderRadius: "50%",
              bgcolor: "#000000",
              border: "2px solid #ed6c02",
              boxShadow: "0 0 0 2px rgba(0,0,0,0.6)",
              pointerEvents: "none",
            }}
          >
            <Box
              component="img"
              src={fullSrc}
              alt=""
              onError={onUnavailable}
              sx={{
                position: "absolute",
                width: solve.width * insetScale,
                height: solve.height * insetScale,
                maxWidth: "none",
                left: diameter / 2 - insetScreenMark.mark.pixel_x * insetScale,
                top: diameter / 2 - insetScreenMark.mark.pixel_y * insetScale,
              }}
            />
            <Box
              component="svg"
              viewBox={`0 0 ${diameter} ${diameter}`}
              aria-hidden
              sx={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
            >
              <ellipse
                cx={diameter / 2}
                cy={diameter / 2}
                rx={Math.max(9, (insetScreenMark.mark.semi_major_px ?? 0) * 1.3 * insetScale)}
                ry={Math.max(9, (insetScreenMark.mark.semi_minor_px ?? 0) * 1.3 * insetScale)}
                transform={`rotate(${insetScreenMark.mark.angle_deg ?? 0} ${diameter / 2} ${diameter / 2})`}
                fill="none"
                stroke="rgba(0,0,0,0.75)"
                strokeWidth={4}
              />
              <ellipse
                cx={diameter / 2}
                cy={diameter / 2}
                rx={Math.max(9, (insetScreenMark.mark.semi_major_px ?? 0) * 1.3 * insetScale)}
                ry={Math.max(9, (insetScreenMark.mark.semi_minor_px ?? 0) * 1.3 * insetScale)}
                transform={`rotate(${insetScreenMark.mark.angle_deg ?? 0} ${diameter / 2} ${diameter / 2})`}
                fill="none"
                stroke="#ed6c02"
                strokeWidth={2}
              />
            </Box>
          </Box>
          {insetLabelBounds && (
            <Box
              sx={{
                position: "absolute",
                zIndex: 2,
                left: insetLabelBounds.left,
                top: insetLabelBounds.top,
                width: insetLabelWidth,
                color: "#f2c27a",
                fontSize: 12,
                fontWeight: 600,
                lineHeight: "16px",
                whiteSpace: "nowrap",
                textShadow: "0 0 3px #000000, 0 0 6px #000000",
                pointerEvents: "none",
              }}
            >
              {insetText}
            </Box>
          )}
        </>
      )}
      <MatchChips
        mainTarget={matchMainTarget}
        inImage={matchInImage}
        compact={compactChips}
        top={chipsAtTop}
      />
    </Box>
  );
}
