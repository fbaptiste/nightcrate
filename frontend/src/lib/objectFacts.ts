import type { GalleryTarget } from "../api/gallery";
import { displayConstellation } from "./constellations";
import { toThreeSigFigs } from "./distanceFormat";
import { displayDsoType, filterTypeCode } from "./dsoTypeNames";

const PC_TO_LY = 3.26156;

export function lightYears(pc: number): number {
  return pc * PC_TO_LY;
}

function scaledNumber(value: number, divisor: number): string {
  const scaled = value / divisor;
  if (scaled < 10) return scaled.toFixed(2);
  if (scaled < 100) return scaled.toFixed(1);
  return scaled.toFixed(0);
}

export function formatLy(ly: number): string {
  const rounded = toThreeSigFigs(ly);
  if (Math.abs(rounded) >= 1_000_000_000) {
    return `${scaledNumber(rounded, 1_000_000_000)} billion`;
  }
  if (Math.abs(rounded) >= 1_000_000) {
    return `${scaledNumber(rounded, 1_000_000)} million`;
  }
  return Math.round(rounded).toLocaleString("en-US");
}

export function formatDistance(
  pc: number,
  estimated: boolean,
  form: "long" | "short",
  withEstimateWord: boolean,
): string {
  const unit = form === "long" ? "light-years" : "ly";
  const prefix = estimated ? "about " : "";
  const suffix = estimated && withEstimateWord ? " (estimate)" : "";
  return `${prefix}${formatLy(lightYears(pc))} ${unit}${suffix}`;
}

export function typeName(objType: string | null): string {
  if (!objType) return "Object";
  return displayDsoType(filterTypeCode(objType));
}

function joinWords(values: string[]): string {
  if (values.length < 2) return values[0] ?? "";
  if (values.length === 2) return `${values[0]} and ${values[1]}`;
  return `${values.slice(0, -1).join(", ")} and ${values.at(-1)}`;
}

export function typeLine(targets: GalleryTarget[]): string {
  if (!targets.length) return "";
  if (targets.length === 1) {
    const constellation = displayConstellation(targets[0].constellation);
    return `${typeName(targets[0].obj_type)} in ${constellation}`;
  }
  const constellations = Array.from(
    new Set(targets.map((target) => displayConstellation(target.constellation))),
  );
  if (constellations.length === 1) return `All in ${constellations[0]}`;
  return `In ${joinWords(constellations)}`;
}

export function targetLabel(target: GalleryTarget): string {
  return target.name;
}

export function countSummary(targets: GalleryTarget[]): { head: string; names: string } {
  const allGalaxies = targets.length > 0 && targets.every(
    (target) => filterTypeCode(target.obj_type ?? "") === "G",
  );
  const shown = targets.slice(0, 3).map(targetLabel);
  const hidden = Math.max(0, targets.length - shown.length);
  return {
    head: `${targets.length} ${allGalaxies ? "galaxies" : "targets"}`,
    names: hidden ? `${shown.join(", ")} and ${hidden} more` : joinWords(shown),
  };
}
