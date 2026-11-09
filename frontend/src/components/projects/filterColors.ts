import type { CSSProperties } from "react";
import type { PaletteMode } from "@mui/material";
import type { Filter } from "@/api/equipment";
import type { ProjectSession } from "@/api/projectSessions";

export type FilterLine =
  | "Lum"
  | "whole"
  | "B"
  | "Hb"
  | "Oiii"
  | "G"
  | "R"
  | "OI"
  | "Ha"
  | "Nii"
  | "Sii"
  | "unknown";

export interface FilterIdentity {
  label: string;
  lineName?: string | null;
  equipmentFilter?: Filter | null;
}

export interface ResolvedFilter {
  label: string;
  lines: FilterLine[];
}

export interface SessionFilterTotal extends ResolvedFilter {
  key: string;
  minutes: number;
}

const COLORS: Record<Exclude<FilterLine, "whole" | "unknown">, { light: string; dark: string }> = {
  B: { light: "#0072B2", dark: "#1A7EBE" },
  Hb: { light: "#56B4E9", dark: "#56B4E9" },
  Oiii: { light: "#56B4E9", dark: "#56B4E9" },
  G: { light: "#009E73", dark: "#009E73" },
  R: { light: "#E69F00", dark: "#E69F00" },
  OI: { light: "#E69F00", dark: "#E69F00" },
  Ha: { light: "#D55E00", dark: "#D55E00" },
  Nii: { light: "#D55E00", dark: "#D55E00" },
  Sii: { light: "#CC79A7", dark: "#CC79A7" },
  Lum: { light: "#2C2C2C", dark: "#E2E0DD" },
};

// Listing order (Fred, 2026-11-08): L and the other whole-spectrum filters,
// then R, G, B, then narrowband lines from red to blue. A filter with several
// lines sorts by its reddest line (the lowest rank among its lines).
const LINE_ORDER: Record<FilterLine, number> = {
  Lum: 0,
  whole: 1,
  R: 2,
  G: 3,
  B: 4,
  Sii: 5,
  Nii: 6,
  Ha: 7,
  OI: 8,
  Oiii: 9,
  Hb: 10,
  unknown: 11,
};

// A multi-line filter's swatch is split red first (longest wavelength first),
// matching the red-to-blue listing order.
const WAVELENGTH_ORDER: Record<FilterLine, number> = {
  Lum: 0,
  whole: 1,
  B: 2,
  Hb: 3,
  Oiii: 4,
  G: 5,
  R: 6,
  OI: 7,
  Ha: 8,
  Nii: 9,
  Sii: 10,
  unknown: 11,
};

const STRIPED_LINES = new Set<FilterLine>(["whole", "Hb", "OI", "Nii"]);
const UNKNOWN_OUTLINE = "#8E8C88";

function normalizeFilter(value: string): string {
  return value
    .trim()
    .toUpperCase()
    .replaceAll("Α", "ALPHA")
    .replaceAll("Β", "BETA")
    .replace(/[^A-Z0-9]/g, "");
}

function canonicalLine(lineName: string | null | undefined): FilterLine | null {
  if (!lineName) return null;
  const normalized = normalizeFilter(lineName);
  if (normalized === "HA") return "Ha";
  if (normalized === "HB") return "Hb";
  if (normalized === "OIII") return "Oiii";
  if (normalized === "SII") return "Sii";
  if (normalized === "NII") return "Nii";
  if (normalized === "OI") return "OI";
  if (normalized === "LUM") return "Lum";
  if (normalized === "R") return "R";
  if (normalized === "G") return "G";
  if (normalized === "B") return "B";
  if (normalized === "UVIR" || normalized === "LP") return "whole";
  if (normalized === "ND" || normalized === "OTHER") return "unknown";
  return null;
}

function lineFromName(label: string): FilterLine {
  const normalized = normalizeFilter(label);
  if (normalized === "HA" || normalized === "HALPHA") return "Ha";
  if (normalized === "HB" || normalized === "HBETA") return "Hb";
  if (normalized === "OIII" || normalized === "O3") return "Oiii";
  if (normalized === "SII" || normalized === "S2") return "Sii";
  if (normalized === "NII" || normalized === "N2") return "Nii";
  if (normalized === "OI" || normalized === "O1") return "OI";
  if (normalized === "L" || normalized === "LUM" || normalized === "LUMINANCE") return "Lum";
  if (normalized === "R" || normalized === "RED") return "R";
  if (normalized === "G" || normalized === "GREEN") return "G";
  if (normalized === "B" || normalized === "BLUE") return "B";
  if (
    normalized === "UVIR" ||
    normalized === "UVIRCUT" ||
    normalized === "NOFILTER" ||
    normalized === "NONE" ||
    normalized === "LP" ||
    normalized === "LIGHTPOLLUTION"
  ) {
    return "whole";
  }
  return "unknown";
}

function orderedDistinct(lines: FilterLine[]): FilterLine[] {
  return [...new Set(lines)].sort((a, b) => WAVELENGTH_ORDER[b] - WAVELENGTH_ORDER[a]);
}

export function resolveFilter(identity: FilterIdentity): ResolvedFilter {
  const passbandLines = identity.equipmentFilter?.passbands
    .map((passband) => canonicalLine(passband.line_name))
    .filter((line): line is FilterLine => line !== null);
  if (passbandLines && passbandLines.length > 0) {
    return { label: identity.label, lines: orderedDistinct(passbandLines) };
  }

  if (identity.lineName && normalizeFilter(identity.lineName) !== "OTHER") {
    return {
      label: identity.label,
      lines: [canonicalLine(identity.lineName) ?? "unknown"],
    };
  }

  return { label: identity.label, lines: [lineFromName(identity.label)] };
}

export function resolveFilterLabel(label: string): ResolvedFilter {
  return resolveFilter({ label });
}

export function sessionFilterIdentity(
  session: ProjectSession,
  filtersById: ReadonlyMap<number, Filter>,
): FilterIdentity {
  const equipmentFilter = session.filter_id == null
    ? null
    : filtersById.get(session.filter_id) ?? null;
  return {
    label:
      equipmentFilter?.model_name ??
      session.filter_label ??
      session.filter_name ??
      session.line_name ??
      "—",
    lineName: session.line_name,
    equipmentFilter,
  };
}

export function resolveSessionFilter(
  session: ProjectSession,
  filtersById: ReadonlyMap<number, Filter>,
): ResolvedFilter {
  return resolveFilter(sessionFilterIdentity(session, filtersById));
}

export function summarizeSessionFilters(
  sessions: ProjectSession[],
  filtersById: ReadonlyMap<number, Filter>,
): SessionFilterTotal[] {
  const totals = new Map<string, SessionFilterTotal>();
  for (const session of sessions) {
    const resolved = resolveSessionFilter(session, filtersById);
    const key = session.filter_id == null
      ? `label:${resolved.label}`
      : `filter:${session.filter_id}`;
    const existing = totals.get(key);
    if (existing) existing.minutes += session.integration_minutes;
    else totals.set(key, { ...resolved, key, minutes: session.integration_minutes });
  }
  return [...totals.values()].sort(compareFilters);
}

export function compareFilters(a: ResolvedFilter, b: ResolvedFilter): number {
  const aOrder = Math.min(...a.lines.map((line) => LINE_ORDER[line]));
  const bOrder = Math.min(...b.lines.map((line) => LINE_ORDER[line]));
  if (aOrder !== bOrder) return aOrder - bOrder;
  if (aOrder === LINE_ORDER.unknown) {
    return a.label.localeCompare(b.label, undefined, { sensitivity: "base" });
  }
  return 0;
}

function lineColor(line: FilterLine, mode: PaletteMode): string {
  if (line === "whole") return COLORS.Lum[mode];
  if (line === "unknown") return "transparent";
  return COLORS[line][mode];
}

function stripe(mode: PaletteMode): string {
  const paper = mode === "dark" ? "rgba(36,39,44,.8)" : "rgba(255,255,255,.75)";
  return `repeating-linear-gradient(135deg, ${paper} 0 2px, transparent 2px 6px)`;
}

function splitGradient(lines: FilterLine[], mode: PaletteMode): string {
  const size = 100 / lines.length;
  const stops = lines.flatMap((line, index) => {
    const color = lineColor(line, mode);
    return [`${color} ${index * size}%`, `${color} ${(index + 1) * size}%`];
  });
  return `linear-gradient(90deg, ${stops.join(", ")})`;
}

export function filterSwatchStyle(
  filter: ResolvedFilter,
  mode: PaletteMode,
  outlineWidth = 2,
): CSSProperties {
  const lines = filter.lines;
  if (lines.length === 1) {
    const line = lines[0];
    if (line === "unknown") {
      return {
        backgroundColor: "transparent",
        boxShadow: `inset 0 0 0 ${outlineWidth}px ${UNKNOWN_OUTLINE}`,
      };
    }
    return {
      backgroundColor: lineColor(line, mode),
      backgroundImage: STRIPED_LINES.has(line) ? stripe(mode) : undefined,
    };
  }

  if (lines.length === 2) {
    const [first, second] = lines;
    const firstStriped = STRIPED_LINES.has(first);
    const secondStriped = STRIPED_LINES.has(second);
    if (firstStriped && !secondStriped) {
      return {
        backgroundColor: lineColor(first, mode),
        backgroundImage: `linear-gradient(135deg, transparent 50%, ${lineColor(second, mode)} 50%), ${stripe(mode)}`,
      };
    }
    if (!firstStriped && secondStriped) {
      return {
        backgroundColor: lineColor(second, mode),
        backgroundImage: `linear-gradient(135deg, ${lineColor(first, mode)} 50%, transparent 50%), ${stripe(mode)}`,
      };
    }
    return {
      backgroundImage: `${firstStriped ? `${stripe(mode)}, ` : ""}linear-gradient(135deg, ${lineColor(first, mode)} 50%, ${lineColor(second, mode)} 50%)`,
      boxShadow: lines.includes("unknown")
        ? `inset 0 0 0 ${outlineWidth}px ${UNKNOWN_OUTLINE}`
        : undefined,
    };
  }

  return {
    backgroundImage: splitGradient(lines, mode),
    boxShadow: lines.includes("unknown")
      ? `inset 0 0 0 ${outlineWidth}px ${UNKNOWN_OUTLINE}`
      : undefined,
  };
}
