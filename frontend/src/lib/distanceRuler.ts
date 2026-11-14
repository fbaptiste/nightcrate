import { formatLy } from "./objectFacts";

export type RulerSize = "small" | "card" | "list" | "viewer" | "info";

export interface MarkerGroup {
  x: number;
  keys: string[];
  estimated: boolean;
}

interface GroupWork extends MarkerGroup {
  x0: number;
  x1: number;
}

export function rulerX(ly: number): number {
  if (!Number.isFinite(ly) || ly <= 0) return 0;
  return Math.max(0, Math.min(100, ((Math.log10(ly) - 2) / 8) * 100));
}

export function groupMarkers(
  items: { key: string; ly: number; estimated: boolean }[],
  widthPx: number,
  markerPx: number,
  mergedMarkerPx: number,
): MarkerGroup[] {
  if (!items.length) return [];
  const safeWidth = Math.max(widthPx, 1);
  const thresholdPct = ((markerPx + 2) / safeWidth) * 100;
  let groups: GroupWork[] = [];
  const clampGroup = (group: GroupWork) => {
    const diameter = group.keys.length > 1 ? mergedMarkerPx : markerPx;
    const inset = diameter / 2 + 4;
    const rawCentrePx = (((group.x0 + group.x1) / 2) / 100) * safeWidth;
    const centrePx = safeWidth < inset * 2
      ? safeWidth / 2
      : Math.max(inset, Math.min(safeWidth - inset, rawCentrePx));
    group.x = (centrePx / safeWidth) * 100;
  };
  const sorted = items
    .map((item) => ({ ...item, x: rulerX(item.ly) }))
    .sort((a, b) => a.x - b.x || a.key.localeCompare(b.key));

  for (const item of sorted) {
    const current = groups.at(-1);
    if (current && item.x - current.x0 < thresholdPct) {
      current.x1 = item.x;
      current.keys.push(item.key);
      current.estimated = false;
      clampGroup(current);
    } else {
      const group = {
        x: item.x,
        x0: item.x,
        x1: item.x,
        keys: [item.key],
        estimated: item.estimated,
      };
      clampGroup(group);
      groups.push(group);
    }
  }

  let merged = true;
  while (merged && groups.length > 1) {
    merged = false;
    const next: GroupWork[] = [];
    for (const group of groups) {
      clampGroup(group);
      const previous = next.at(-1);
      if (previous) {
        clampGroup(previous);
        const previousDiameter = previous.keys.length > 1 ? mergedMarkerPx : markerPx;
        const groupDiameter = group.keys.length > 1 ? mergedMarkerPx : markerPx;
        const gapPx = ((group.x - previous.x) / 100) * safeWidth;
        if (gapPx < (previousDiameter + groupDiameter) / 2 + 2) {
          previous.x1 = group.x1;
          previous.keys.push(...group.keys);
          previous.estimated = false;
          clampGroup(previous);
          merged = true;
          continue;
        }
      }
      next.push({ ...group, keys: [...group.keys] });
    }
    groups = next;
  }

  return groups.map(({ x, keys, estimated }) => ({ x, keys, estimated }));
}

function splitScale(value: string): { number: string; scale: string } {
  const match = value.match(/^(.+?) (million|billion)$/);
  return match ? { number: match[1], scale: match[2] } : { number: value, scale: "" };
}

export function valueLabel(
  targets: { ly: number; estimated: boolean }[],
  form: "long" | "short",
  withEstimateWord: boolean,
): string | null {
  if (!targets.length) return null;
  const sorted = [...targets].sort((a, b) => a.ly - b.ly);
  const lo = sorted[0];
  const hi = sorted.at(-1)!;
  const low = splitScale(formatLy(lo.ly));
  const high = splitScale(formatLy(hi.ly));
  let value = formatLy(lo.ly);
  if (lo.ly !== hi.ly && formatLy(lo.ly) !== formatLy(hi.ly)) {
    value = low.scale === high.scale
      ? `${low.number}–${formatLy(hi.ly)}`
      : `${formatLy(lo.ly)} – ${formatLy(hi.ly)}`;
  }
  const unit = form === "long" ? "light-years" : "ly";
  if (sorted.length === 1 && lo.estimated) {
    return `about ${value} ${unit}${withEstimateWord ? " (estimate)" : ""}`;
  }
  return `${value} ${unit}`;
}

export function labelAnchor(
  xLo: number,
  xHi: number,
  size: RulerSize,
): "start" | "center" | "end" {
  const midpoint = (xLo + xHi) / 2;
  const end = size === "info" ? 70 : 66;
  const start = size === "info" ? 12 : 25;
  if (midpoint > end) return "end";
  if (midpoint < start) return "start";
  return "center";
}
