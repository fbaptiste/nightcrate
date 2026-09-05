import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";
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
  // A list grows with the catalog and would eventually outrun the dialog, so
  // the choice is a select: one row whatever the catalog holds.
  // No reset effect here: RigsPage gives this dialog a key tied to `open`, so a
  // reopen is a fresh mount and `chosenId` starts empty. Resetting in a
  // useEffect instead would paint one frame carrying the previous selection —
  // with "Add this rig" already enabled — before the effect cleared it.
  const [chosenId, setChosenId] = useState<number | "">("");

  // The API orders rigs for the user's own list (owned first, then sort_order).
  // That ordering means nothing in a catalog you're picking from, so sort by
  // name — locale-aware so "DWARF II" and "Seestar S30" collate sensibly.
  const options = [...available].sort((a, b) => a.name.localeCompare(b.name));
  const chosen = available.find((r) => r.id === chosenId) ?? null;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>New Rig</DialogTitle>
      <DialogContent>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          Pre-defined rigs
        </Typography>
        <Typography variant="body2" sx={{ color: "text.secondary", mb: 1.5 }}>
          Ready-made, with the optics, camera and filters already set up.
        </Typography>
        {available.length > 0 ? (
          <>
            <TextField
              select
              fullWidth
              size="small"
              label="Choose a rig"
              value={chosenId}
              onChange={(e) =>
                setChosenId(e.target.value === "" ? "" : Number(e.target.value))
              }
            >
              {options.map((rig) => (
                <MenuItem key={rig.id} value={rig.id}>
                  {rig.name}
                </MenuItem>
              ))}
            </TextField>
            {/* The spec sits below rather than inside each option: a menu row
                holding two lines of detail is unreadable at a glance. */}
            <Typography
              variant="body2"
              sx={{ color: "text.secondary", mt: 1, minHeight: 20 }}
            >
              {chosen ? specLine(chosen) : ""}
            </Typography>
            <Button
              variant="contained"
              disabled={!chosen}
              onClick={() => chosen && onChoosePredefined(chosen)}
              sx={{ mt: 1.5 }}
            >
              Add this rig
            </Button>
          </>
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
