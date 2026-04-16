import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardActions from "@mui/material/CardActions";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import RestoreIcon from "@mui/icons-material/Restore";
import StarIcon from "@mui/icons-material/Star";
import StarOutlineIcon from "@mui/icons-material/StarOutline";
import type { Rig } from "@/api/rigs";

interface RigCardProps {
  rig: Rig;
  selected?: boolean;
  onSelect: (rig: Rig) => void;
  onEdit: (rig: Rig) => void;
  onClone: (id: number) => void;
  onDelete: (id: number) => void;
  onRestore: (id: number) => void;
  onSetDefault: (id: number) => void;
}

const SAMPLING_COLORS: Record<string, { bg: string; text: string }> = {
  well_sampled: { bg: "#1976d2", text: "#ffffff" },
  oversampled: { bg: "#ed6c02", text: "#ffffff" },
  undersampled: { bg: "#7b1fa2", text: "#ffffff" },
};

const SAMPLING_LABELS: Record<string, string> = {
  well_sampled: "Well Sampled",
  oversampled: "Oversampled",
  undersampled: "Undersampled",
};

function formatFilterSummary(rig: Rig): string {
  if (rig.filter_slots.length > 0) {
    const slotNames = rig.filter_slots
      .sort((a, b) => a.slot_number - b.slot_number)
      .map((s) => s.filter_name)
      .join(" \u00b7 ");
    return `${rig.filter_wheel_positions}-pos: ${slotNames}`;
  }
  if (rig.single_filter_name) {
    return `Filter: ${rig.single_filter_name}`;
  }
  return "No filter wheel";
}

export default function RigCard({
  rig,
  selected,
  onSelect,
  onEdit,
  onClone,
  onDelete,
  onRestore,
  onSetDefault,
}: RigCardProps) {
  const calc = rig.calculators;
  const scale = calc.image_scale_arcsec_per_pixel;
  const [fovW, fovH] = calc.field_of_view_arcmin;
  const fl = rig.effective_focal_length_mm;
  const ratio = rig.effective_focal_ratio;
  const statsLine = `${fl}mm \u00b7 f/${ratio} \u00b7 ${scale.toFixed(2)}\u2033/px \u00b7 ${fovW.toFixed(1)}\u00d7${fovH.toFixed(1)}\u2032`;

  const sampling = calc.sampling_assessment;
  const samplingColor = SAMPLING_COLORS[sampling.assessment] ?? {
    bg: "#888888",
    text: "#ffffff",
  };
  const samplingLabel =
    SAMPLING_LABELS[sampling.assessment] ?? sampling.assessment;

  return (
    <Card
      variant="outlined"
      sx={{
        opacity: rig.active ? 1 : 0.6,
        cursor: "pointer",
        outline: selected ? 2 : 0,
        outlineColor: "primary.main",
        "&:hover": { boxShadow: 4 },
      }}
      onClick={() => onSelect(rig)}
    >
      <CardContent sx={{ pb: 1 }}>
        {/* Name + default chip */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
          <Typography variant="h6" fontWeight="bold">
            {rig.name}
          </Typography>
          {rig.is_default && (
            <Chip label="Default" color="primary" size="small" />
          )}
        </Box>

        {/* OTA line */}
        <Typography variant="body2" color="text.secondary">
          {rig.telescope_name} &mdash; {rig.telescope_config_name}
        </Typography>

        {/* Stats line (above camera) */}
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {statsLine}
        </Typography>

        {/* Camera line */}
        <Typography variant="body2" color="text.secondary">
          {rig.camera_name}
        </Typography>

        {/* Filter summary (above mount) */}
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {formatFilterSummary(rig)}
        </Typography>

        {/* Mount line */}
        {rig.mount_name && (
          <Typography variant="body2" color="text.secondary">
            Mount: {rig.mount_name}
          </Typography>
        )}

        {/* Sampling badge */}
        <Box sx={{ mt: 1 }}>
          <Chip
            label={samplingLabel}
            size="small"
            sx={{
              bgcolor: samplingColor.bg,
              color: samplingColor.text,
              fontWeight: 600,
            }}
          />
        </Box>

        {/* Warnings */}
        {rig.warnings.length > 0 && (
          <Alert
            severity="warning"
            variant="outlined"
            sx={{ mt: 1, py: 0, fontSize: "0.75rem" }}
          >
            {rig.warnings.map((w, i) => (
              <Typography key={i} variant="caption" component="div">
                {w.message}
              </Typography>
            ))}
          </Alert>
        )}
      </CardContent>

      <CardActions
        sx={{ px: 2, pt: 0 }}
        onClick={(e) => e.stopPropagation()}
      >
        <Tooltip title="Edit" arrow>
          <IconButton size="small" onClick={() => onEdit(rig)}>
            <EditIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Clone" arrow>
          <IconButton size="small" onClick={() => onClone(rig.id)}>
            <ContentCopyIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        {rig.active && (
          <Tooltip
            title={rig.is_default ? "Default rig" : "Set as default"}
            arrow
          >
            <IconButton
              size="small"
              onClick={() => onSetDefault(rig.id)}
              sx={{ color: rig.is_default ? "warning.main" : undefined }}
            >
              {rig.is_default ? (
                <StarIcon fontSize="small" />
              ) : (
                <StarOutlineIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
        )}
        {rig.active ? (
          <Tooltip title="Delete" arrow>
            <IconButton size="small" onClick={() => onDelete(rig.id)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        ) : (
          <Tooltip title="Restore" arrow>
            <IconButton size="small" onClick={() => onRestore(rig.id)}>
              <RestoreIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </CardActions>
    </Card>
  );
}
