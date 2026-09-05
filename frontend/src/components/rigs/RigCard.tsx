import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActions from "@mui/material/CardActions";
import CardContent from "@mui/material/CardContent";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import RestoreIcon from "@mui/icons-material/Restore";
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
  /** Claim/unclaim the rig as the user's own. Omitted where it doesn't apply. */
  onToggleMine?: (id: number, isMine: boolean) => void;
}


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
  // A wheel with nothing assigned is not the same as no wheel: saying "No
  // filter wheel" here contradicted the edit dialog, which showed the wheel
  // the rig really does have.
  if (rig.filter_wheel_name) {
    const positions = rig.filter_wheel_positions;
    return `${rig.filter_wheel_name}${positions ? ` (${positions}-pos)` : ""} \u2014 no filters assigned`;
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
  onToggleMine,
}: RigCardProps) {
  const calc = rig.calculators;
  const scale = calc.image_scale_arcsec_per_pixel;
  const [fovW, fovH] = calc.field_of_view_arcmin;
  const fl = rig.effective_focal_length_mm;
  const ratio = rig.effective_focal_ratio;
  const statsLine = `${fl}mm \u00b7 f/${ratio} \u00b7 ${scale.toFixed(2)}\u2033/px \u00b7 ${fovW.toFixed(1)}\u00d7${fovH.toFixed(1)}\u2032`;

  return (
    <Card
      variant="outlined"
      sx={{
        opacity: rig.active ? 1 : 0.6,
        cursor: "pointer",
        outline: selected ? 2 : 0,
        outlineColor: "primary.main",
        "&:hover": { boxShadow: 4 },
        position: "relative",
      }}
      onClick={() => onSelect(rig)}
    >
      {/* Default toggle — upper right */}
      {rig.active && (
        <Button
          size="small"
          variant={rig.is_default ? "contained" : "outlined"}
          onClick={(e) => { e.stopPropagation(); onSetDefault(rig.id); }}
          sx={{
            position: "absolute",
            top: 8,
            right: 8,
            textTransform: "none",
            fontSize: "0.7rem",
            px: 1,
            py: 0.125,
            minWidth: 0,
          }}
        >
          default
        </Button>
      )}

      <CardContent sx={{ pb: 1 }}>
        {/* Name */}
        <Typography variant="h6" fontWeight="bold" sx={{ mb: 0.5, pr: 4 }}>
          {rig.name}
        </Typography>

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
        {/* An explicit button, not a star: a star means favourite or default
            elsewhere in the app, and this is neither — it is membership. */}
        {onToggleMine && (
          <Button
            size="small"
            variant={rig.is_mine ? "outlined" : "contained"}
            onClick={() => onToggleMine(rig.id, !rig.is_mine)}
            sx={{ textTransform: "none", mr: 0.5 }}
          >
            {rig.is_mine ? "Remove from my rigs" : "Add to my rigs"}
          </Button>
        )}
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
        {/* A catalog rig is claimed or released with the star — retiring one
            makes no sense, and produced a confusing "Retired Rigs" entry for a
            telescope that still exists. Only self-built rigs retire. */}
        {rig.source === "user" &&
          (rig.active ? (
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
          ))}
      </CardActions>
    </Card>
  );
}
