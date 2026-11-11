import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import GpsFixedIcon from "@mui/icons-material/GpsFixed";
import TrackChangesIcon from "@mui/icons-material/TrackChanges";

interface Props {
  mainTarget: boolean;
  inImage: boolean;
  compact: boolean;
  top?: boolean;
}

function MatchChip({
  label,
  compact,
  kind,
}: {
  label: string;
  compact: boolean;
  kind: "target" | "image";
}) {
  const icon =
    kind === "target" ? (
      <TrackChangesIcon sx={{ fontSize: 14 }} />
    ) : (
      <GpsFixedIcon sx={{ fontSize: 14 }} />
    );
  const chip = (
    <Box
      role={compact ? "img" : undefined}
      aria-label={compact ? label : undefined}
      sx={{
        height: 24,
        minWidth: compact ? 24 : 0,
        px: compact ? 0 : "8px",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "5px",
        borderRadius: 12,
        bgcolor: kind === "target" ? "rgba(0,80,70,0.82)" : "rgba(0,0,0,0.66)",
        border:
          kind === "target"
            ? "1px solid rgba(120,220,205,0.55)"
            : "1px solid rgba(255,255,255,0.32)",
        color: "#ffffff",
        fontSize: 11.5,
        fontWeight: 600,
        whiteSpace: "nowrap",
        pointerEvents: compact ? "auto" : "none",
      }}
    >
      {icon}
      {!compact && label}
    </Box>
  );
  return compact ? <Tooltip title={label}>{chip}</Tooltip> : chip;
}

export default function MatchChips({ mainTarget, inImage, compact, top = false }: Props) {
  if (!mainTarget && !inImage) return null;
  return (
    <Box
      sx={{
        position: "absolute",
        zIndex: 3,
        left: compact ? 6 : 8,
        ...(top
          ? { top: compact ? 6 : 8 }
          : { bottom: compact ? 6 : 8 }),
        display: "flex",
        gap: "5px",
      }}
    >
      {mainTarget && (
        <MatchChip label="Main target" compact={compact} kind="target" />
      )}
      {inImage && (
        <MatchChip
          label="In the plate-solved image"
          compact={compact}
          kind="image"
        />
      )}
    </Box>
  );
}
