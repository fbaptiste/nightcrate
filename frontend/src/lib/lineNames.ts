// Bandpass line-name vocabulary — mirrors the backend filter_passband.line_name
// CHECK (migration 0005) and project_session/project_filter_goal (migration 0035).

export const LINE_NAMES = [
  "Ha",
  "Hb",
  "Oiii",
  "Sii",
  "Nii",
  "OI",
  "Lum",
  "R",
  "G",
  "B",
  "R+",
  "UVIR",
  "LP",
  "ND",
  "other",
] as const;

export type LineName = (typeof LINE_NAMES)[number];

// Human-readable labels for the bandpass dropdowns.
export const LINE_NAME_LABELS: Record<string, string> = {
  Ha: "H-alpha (656 nm)",
  Hb: "H-beta (486 nm)",
  Oiii: "OIII (501 nm)",
  Sii: "SII (672 nm)",
  Nii: "NII (658 nm)",
  OI: "OI (630 nm)",
  Lum: "Luminance",
  R: "Red",
  G: "Green",
  B: "Blue",
  "R+": "Red-enhanced",
  UVIR: "UV/IR cut",
  LP: "Light pollution",
  ND: "Neutral density",
  other: "Other",
};

export function lineLabel(line: string): string {
  return LINE_NAME_LABELS[line] ?? line;
}

// Index for canonical ordering (matches the backend LINE_NAMES order).
export function lineOrder(line: string): number {
  const i = (LINE_NAMES as readonly string[]).indexOf(line);
  return i === -1 ? LINE_NAMES.length : i;
}
