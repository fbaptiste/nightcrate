/**
 * Human-readable labels + categorical colors for OpenNGC obj_type values.
 * Colors avoid red/green to stay colorblind-safe; the four buckets use
 * blue (galaxies), orange (nebulae), teal (clusters), and neutral gray.
 */
import { RIG_BLUE, RIG_ORANGE, RIG_TEAL } from "./rigColors";

export const DSO_TYPE_DISPLAY: Record<string, string> = {
  G: "Galaxy",
  GPair: "Galaxy pair",
  GTrpl: "Galaxy triplet",
  GGroup: "Galaxy group",
  HII: "HII region",
  EmN: "Emission nebula",
  RfN: "Reflection nebula",
  PN: "Planetary nebula",
  OCl: "Open cluster",
  GCl: "Globular cluster",
  "Cl+N": "Cluster + nebula",
  SNR: "Supernova remnant",
  DrkN: "Dark nebula",
  Neb: "Nebula",
  "*Ass": "Stellar association",
  Nova: "Nova",
  "*": "Star",
  "**": "Double star",
  Other: "Other",
};

type TypeBucket = "galaxy" | "nebula" | "cluster" | "other";

const TYPE_BUCKET: Record<string, TypeBucket> = {
  G: "galaxy",
  GPair: "galaxy",
  GTrpl: "galaxy",
  GGroup: "galaxy",
  HII: "nebula",
  EmN: "nebula",
  RfN: "nebula",
  PN: "nebula",
  SNR: "nebula",
  DrkN: "nebula",
  Neb: "nebula",
  "Cl+N": "nebula",
  OCl: "cluster",
  GCl: "cluster",
  "*Ass": "other",
  Nova: "other",
  "*": "other",
  "**": "other",
  Other: "other",
};

export function displayDsoType(objType: string): string {
  return DSO_TYPE_DISPLAY[objType] ?? objType;
}

export function dsoTypeColor(objType: string): string {
  const bucket = TYPE_BUCKET[objType] ?? "other";
  switch (bucket) {
    case "galaxy":
      return RIG_BLUE;
    case "nebula":
      return RIG_ORANGE;
    case "cluster":
      return RIG_TEAL;
    default:
      return "#888888";
  }
}
