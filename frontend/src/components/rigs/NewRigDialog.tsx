import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import type { Rig } from "@/api/rigs";

interface NewRigDialogProps {
  open: boolean;
  /** Pre-defined rigs not already in the user's list. */
  available: Rig[];
  onClose: () => void;
  /** Adopt a pre-defined rig. */
  onChoosePredefined: (rig: Rig) => void;
  /** Fall through to the normal rig-creation form. */
  onChooseCustom: () => void;
}

/** One-line spec so a pre-defined rig is recognisable without opening it. */
function specLine(rig: Rig): string {
  const scale = rig.calculators.image_scale_arcsec_per_pixel;
  const parts = [
    `${rig.effective_focal_length_mm}mm`,
    `f/${rig.effective_focal_ratio}`,
    `${scale.toFixed(2)}″/px`,
    rig.camera_name,
  ];
  if (rig.filter_slots.length > 0) {
    parts.push(`${rig.filter_slots.length} filters`);
  }
  return parts.join(" · ");
}

/**
 * First step of adding a rig: pick a ready-made one or build your own.
 *
 * Pre-defined rigs are seeded catalog entries whose optics, camera and filters
 * are fixed by the manufacturer, so adopting one is a choice rather than a
 * build. RigsPage skips this dialog entirely when none are left to add.
 */
export default function NewRigDialog({
  open,
  available,
  onClose,
  onChoosePredefined,
  onChooseCustom,
}: NewRigDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>New Rig</DialogTitle>
      <DialogContent>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          Pre-defined rigs
        </Typography>
        <Typography variant="body2" sx={{ color: "text.secondary", mb: 1 }}>
          Ready-made, with the optics, camera and filters already set up.
        </Typography>
        {available.length > 0 ? (
          <List dense disablePadding>
            {available.map((rig) => (
              <ListItemButton
                key={rig.id}
                onClick={() => onChoosePredefined(rig)}
                sx={{ borderRadius: 1 }}
              >
                <ListItemText primary={rig.name} secondary={specLine(rig)} />
              </ListItemButton>
            ))}
          </List>
        ) : (
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            You&rsquo;ve added all of them.
          </Typography>
        )}

        <Divider sx={{ my: 2 }} />

        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          Custom rig
        </Typography>
        <Typography variant="body2" sx={{ color: "text.secondary", mb: 1 }}>
          Build one from your own equipment.
        </Typography>
        <Button variant="outlined" onClick={onChooseCustom}>
          Build a custom rig
        </Button>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
      </DialogActions>
    </Dialog>
  );
}
