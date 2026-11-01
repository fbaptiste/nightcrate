import { alpha } from "@mui/material/styles";

import { scaleFrom, type HeaderHints, type ScaleHint } from "./hintModel";

export const buttonSx = { minHeight: 40 } as const;
export const panelSx = {
  bgcolor: "background.paper",
  border: 1,
  borderColor: "divider",
  borderRadius: "8px",
  p: 2,
  display: "grid",
  gap: "14px",
} as const;

export function noteSx(color: string) {
  return {
    borderRadius: "6px",
    p: "10px 12px",
    fontSize: 13,
    bgcolor: alpha(color, 0.12),
    border: `1px solid ${alpha(color, 0.4)}`,
  };
}

export function formatPosition(ra: number | null, dec: number | null): string {
  if (ra == null || dec == null) return "No coordinates found";
  const hours = ra / 15;
  const h = Math.floor(hours);
  const m = Math.floor((hours - h) * 60);
  const s = ((hours - h) * 60 - m) * 60;
  const abs = Math.abs(dec);
  const d = Math.floor(abs);
  const dm = Math.floor((abs - d) * 60);
  const ds = ((abs - d) * 60 - dm) * 60;
  const sign = dec >= 0 ? "+" : "−";
  return (
    `${String(h).padStart(2, "0")}h ${String(m).padStart(2, "0")}m ` +
    `${s.toFixed(1)}s, ${sign}${String(d).padStart(2, "0")}° ` +
    `${String(dm).padStart(2, "0")}′ ${ds.toFixed(0)}″`
  );
}

export function scaleValue(scale: ScaleHint, header: HeaderHints): number | null {
  if (scale.kind === "header") return header.scaleArcsec;
  if (scale.kind === "none") return null;
  const value = scaleFrom(scale);
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function formatHintNumber(
  value: number,
  kind: "scale" | "focalLength" | "pixelSize",
): string {
  const options: Intl.NumberFormatOptions =
    kind === "scale"
      ? { maximumSignificantDigits: 3, useGrouping: false }
      : { maximumFractionDigits: kind === "focalLength" ? 1 : 2, useGrouping: false };
  return new Intl.NumberFormat("en-US", options).format(value);
}
