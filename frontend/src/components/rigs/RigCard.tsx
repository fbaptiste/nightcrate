import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
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
  if (rig.filter_wheel_name) {
    const count = rig.filter_slots.length;
    const positions = rig.filter_wheel_positions;
    const filled = count > 0 ? `${count} of ${positions} filters` : "no filters assigned";
    return `${rig.filter_wheel_name} \u2014 ${filled}`;
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
  onToggleMine,
}: RigCardProps) {
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
      {/* Default marker — upper right. A state and an action read differently:
          an outlined vs contained button both labelled "default" was
          indistinguishable in dark theme, so the wording and the component
          change, not just the fill. Only shown for rigs the user owns — an
          unclaimed catalog rig can't be your default. */}
      {rig.active && rig.is_mine && (
        rig.is_default ? (
          <Chip
            size="small"
            label="Default"
            color="primary"
            sx={{ position: "absolute", top: 8, right: 8, height: 20, fontSize: "0.7rem" }}
          />
        ) : (
          <Button
            size="small"
            variant="text"
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
            Set as default
          </Button>
        )
      )}

      <CardContent sx={{ pb: 1 }}>
        <Typography variant="h6" fontWeight="bold" sx={{ mb: 0.25, pr: 10 }}>
          {rig.name}
        </Typography>

        {rig.description && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
            {rig.description}
          </Typography>
        )}

        <Typography variant="body2" color="text.secondary">
          {rig.telescope_name} &mdash; {rig.telescope_config_name}
        </Typography>

        {/* The three optical numbers that identify a rig at a glance. */}
        <Typography variant="body2" color="text.secondary">
          {rig.aperture_mm}mm aperture &middot; {rig.effective_focal_length_mm}mm
          &middot; f/{rig.effective_focal_ratio}
        </Typography>

        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {formatFilterSummary(rig)}
        </Typography>

        {rig.warnings.length > 0 && (
          <Typography variant="caption" color="warning.main" sx={{ display: "block", mt: 1 }}>
            {rig.warnings.length} warning{rig.warnings.length > 1 ? "s" : ""}
          </Typography>
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
        {/* One delete affordance in one place. What it means depends on where
            the rig came from: a self-built rig retires, a pre-defined one is
            simply removed from the user's rigs and returns to the New Rig
            offer list — it is a catalog entry, not something to destroy. */}
        {rig.source === "seed" ? (
          onToggleMine && (
            <Tooltip title="Remove from my rigs" arrow>
              <IconButton size="small" onClick={() => onToggleMine(rig.id, false)}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )
        ) : rig.active ? (
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
