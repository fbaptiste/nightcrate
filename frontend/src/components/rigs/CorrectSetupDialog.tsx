import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import { correctRigSetup, type EquipmentOptions, type RigPartsInput, type RigSetup } from "@/api/rigs";
import RigPartsForm from "@/components/rigs/RigPartsForm";

interface CorrectSetupDialogProps {
  open: boolean;
  setup: RigSetup | null;
  options: EquipmentOptions;
  onClose: () => void;
  onSaved: () => void;
}

function formatSetupDate(value: string): string {
  const isoValue = value.includes("T") ? value : value.replace(" ", "T");
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(isoValue) ? isoValue : `${isoValue}Z`);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

function setupInput(setup: RigSetup): RigPartsInput {
  return {
    telescope_configuration_id: setup.parts.telescope_configuration_id,
    camera_id: setup.parts.camera_id,
    filter_wheel_id: setup.parts.filter_wheel_id,
    single_filter_id: setup.parts.single_filter_id,
    mount_id: setup.parts.mount_id,
    focuser_id: setup.parts.focuser_id,
    oag_id: setup.parts.oag_id,
    guide_scope_id: setup.parts.guide_scope_id,
    guide_camera_id: setup.parts.guide_camera_id,
    computer_id: setup.parts.computer_id,
    software_ids: setup.parts.software.map((item) => item.id),
    filter_slots: setup.parts.filter_slots.map(({ slot_number, filter_id }) => ({
      slot_number,
      filter_id,
    })),
  };
}

export default function CorrectSetupDialog({
  open,
  setup,
  options,
  onClose,
  onSaved,
}: CorrectSetupDialogProps) {
  const [value, setValue] = useState<RigPartsInput | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open && setup) {
      setValue(setupInput(setup));
      setError(null);
    }
  }, [open, setup]);

  const handleSave = async () => {
    if (!setup || !value) return;
    if (!value.telescope_configuration_id || !value.camera_id) {
      setError("Telescope and camera are required.");
      return;
    }
    setSaving(true);
    try {
      await correctRigSetup(setup.id, value);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to correct setup");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        {setup ? `Correct setup until ${formatSetupDate(setup.until_at)}` : "Correct setup"}
      </DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {value && (
          <RigPartsForm
            key={setup?.id}
            value={value}
            onChange={setValue}
            options={options}
            partSources={[setup!.parts]}
          />
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>Cancel</Button>
        <Button variant="contained" onClick={handleSave} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
