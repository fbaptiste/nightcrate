/**
 * Colorblind-safe palette for the planner's per-target quality chip.
 * Mirrors the rig-calculator palette (blue / orange / neutral).
 */

import type { QualityLabel } from "@/api/planner";
import { RIG_BLUE, RIG_BLUE_LIGHT, RIG_ORANGE } from "@/lib/rigColors";

export interface ScoreChipStyle {
  background: string;
  textColor: string;
}

const CHIP_STYLE: Record<QualityLabel, ScoreChipStyle> = {
  Excellent: { background: RIG_BLUE, textColor: "#ffffff" },
  Good: { background: RIG_BLUE_LIGHT, textColor: "rgba(0, 0, 0, 0.87)" },
  Fair: { background: "#9e9e9e", textColor: "#ffffff" },
  Poor: { background: RIG_ORANGE, textColor: "#ffffff" },
};

export function scoreChipStyle(label: QualityLabel): ScoreChipStyle {
  return CHIP_STYLE[label];
}
