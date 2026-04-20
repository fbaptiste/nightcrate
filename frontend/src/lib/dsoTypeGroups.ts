/**
 * User-facing DSO type-group metadata, mirroring the backend's
 * ``services/dso_type_groups.py`` dispatch. The backend is the source of
 * truth — this file only carries display order + color hints for the
 * frontend when the facets endpoint doesn't already populate those.
 */
import { RIG_BLUE, RIG_ORANGE, RIG_TEAL } from "./rigColors";

export interface TypeGroupStyle {
  bg: string;
  label: string; // short label variant for tight chip display
}

// Map from group name → chip color. The backend's TYPE_GROUPS order
// carries the display ordering; this map just adds a color.
export const TYPE_GROUP_STYLES: Record<string, TypeGroupStyle> = {
  Galaxy: { bg: RIG_BLUE, label: "Galaxy" },
  "Galaxy Group": { bg: RIG_BLUE, label: "Galaxy Group" },
  "Open Cluster": { bg: RIG_TEAL, label: "Open Cluster" },
  "Globular Cluster": { bg: RIG_TEAL, label: "Globular Cluster" },
  "Emission Nebula": { bg: RIG_ORANGE, label: "Emission Nebula" },
  "Reflection Nebula": { bg: RIG_ORANGE, label: "Reflection Nebula" },
  "Planetary Nebula": { bg: RIG_ORANGE, label: "Planetary Nebula" },
  "Dark Nebula": { bg: "#555555", label: "Dark Nebula" },
  "Supernova Remnant": { bg: RIG_ORANGE, label: "Supernova Remnant" },
  "Other Nebula": { bg: RIG_ORANGE, label: "Other Nebula" },
  "Stellar Association": { bg: "#888888", label: "Stellar Association" },
  "Star / Multiple": { bg: "#888888", label: "Star / Multiple" },
  Other: { bg: "#888888", label: "Other" },
};

export function typeGroupStyle(name: string): TypeGroupStyle {
  return TYPE_GROUP_STYLES[name] ?? { bg: "#888888", label: name };
}
