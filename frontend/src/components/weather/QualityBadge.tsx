import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { scoreToBackground, scoreToLabel, scoreToTextColor } from "../../lib/weatherColors";

type BadgeSize = "small" | "medium" | "large";

interface QualityBadgeProps {
  score: number;
  label?: string;
  metricName?: string;
  size?: BadgeSize;
  showLabel?: boolean;
  tooltip?: string;
}

const SIZE_MAP: Record<BadgeSize, { box: number; score: string; label: string }> = {
  small: { box: 40, score: "0.85rem", label: "0.6rem" },
  medium: { box: 56, score: "1.1rem", label: "0.7rem" },
  large: { box: 72, score: "1.4rem", label: "0.8rem" },
};

export default function QualityBadge({
  score,
  label,
  metricName,
  size = "medium",
  showLabel = true,
  tooltip,
}: QualityBadgeProps) {
  const { box, score: scoreFontSize, label: labelFontSize } = SIZE_MAP[size];
  const bg = scoreToBackground(score);
  const textColor = scoreToTextColor(score);
  const displayLabel = label ?? scoreToLabel(score);

  const badge = (
    <Box sx={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: 0.25 }}>
      {metricName && (
        <Typography
          variant="caption"
          sx={{ fontSize: labelFontSize, color: "text.secondary", lineHeight: 1.2 }}
        >
          {metricName}
        </Typography>
      )}
      <Box
        sx={{
          width: box,
          height: box,
          borderRadius: "50%",
          backgroundColor: bg,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <Typography
          sx={{
            fontSize: scoreFontSize,
            fontWeight: 700,
            color: textColor,
            lineHeight: 1,
          }}
        >
          {Math.round(score)}
        </Typography>
      </Box>
      {showLabel && (
        <Typography
          variant="caption"
          sx={{ fontSize: labelFontSize, color: "text.secondary", lineHeight: 1.2 }}
        >
          {displayLabel}
        </Typography>
      )}
    </Box>
  );

  if (tooltip) {
    return <Tooltip title={tooltip}>{badge}</Tooltip>;
  }

  return badge;
}
