/**
 * Per-target quality chip for the Target Planner list + detail header
 * (v0.21.0 scoring).
 *
 * Renders either ``NN · Excellent`` with a colored background, or ``—``
 * as a neutral outlined chip for gated (null-score) targets. Tooltip
 * surfaces gate-failure reasons for the unscored case.
 */
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";

import type { QualityLabel } from "@/api/planner";
import { scoreChipStyle } from "@/lib/plannerScoreColors";

interface ScoreChipProps {
  scorePct: number | null;
  qualityLabel: QualityLabel | null;
  /** Used only for the unscored tooltip. */
  gateFailures?: string[];
  /** Compact for list cards; larger + bolder for the detail header. */
  size?: "small" | "medium";
}

export function ScoreChip({
  scorePct,
  qualityLabel,
  gateFailures,
  size = "small",
}: ScoreChipProps) {
  const height = size === "small" ? 20 : 24;
  const fontSize = size === "small" ? "0.72rem" : "0.78rem";

  if (scorePct === null || qualityLabel === null) {
    const tooltip =
      gateFailures && gateFailures.length > 0
        ? `Not scored: ${gateFailures[0]}`
        : "Not scored — no quality assessment for this target tonight.";
    return (
      <Tooltip title={tooltip} placement="top" arrow>
        <Chip
          label="—"
          size={size}
          variant="outlined"
          sx={{
            height,
            "& .MuiChip-label": { px: 0.85, fontSize, color: "text.secondary" },
          }}
        />
      </Tooltip>
    );
  }

  const style = scoreChipStyle(qualityLabel);
  return (
    <Tooltip
      title={`${scorePct} of 100 · ${qualityLabel}`}
      placement="top"
      arrow
    >
      <Chip
        label={`${scorePct} · ${qualityLabel}`}
        size={size}
        sx={{
          height,
          backgroundColor: style.background,
          color: style.textColor,
          fontWeight: 600,
          "& .MuiChip-label": { px: 0.85, fontSize },
        }}
      />
    </Tooltip>
  );
}

