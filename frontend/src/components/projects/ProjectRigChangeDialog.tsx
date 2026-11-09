import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Typography from "@mui/material/Typography";
import { fetchEquipmentOptions, fetchRig, type RigPartsInput } from "@/api/rigs";
import { setProjectRigChange, type ProjectRigSetups } from "@/api/projects";
import RigPartsForm from "@/components/rigs/RigPartsForm";

interface Props {
  open: boolean;
  projectId: number;
  projectName: string;
  rig: ProjectRigSetups;
  onClose: () => void;
  onSaved: () => void;
}

function cloneParts(parts: RigPartsInput): RigPartsInput {
  return {
    ...parts,
    software_ids: [...parts.software_ids],
    filter_slots: parts.filter_slots.map((slot) => ({ ...slot })),
  };
}

export default function ProjectRigChangeDialog({
  open,
  projectId,
  projectName,
  rig,
  onClose,
  onSaved,
}: Props) {
  const { data: options } = useQuery({
    queryKey: ["equipment-options"],
    queryFn: fetchEquipmentOptions,
    enabled: open,
  });
  const { data: currentRig } = useQuery({
    queryKey: ["rig", rig.rig_id],
    queryFn: () => fetchRig(rig.rig_id),
    enabled: open,
  });
  const [value, setValue] = useState<RigPartsInput>(() =>
    cloneParts(rig.change ?? rig.base_parts),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setValue(cloneParts(rig.change ?? rig.base_parts));
    setError(null);
  }, [open, rig]);

  const save = async () => {
    if (!value.telescope_configuration_id || !value.camera_id) {
      setError("Telescope and camera are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await setProjectRigChange(projectId, rig.rig_id, value);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save the project setup");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogTitle>{rig.rig_name}, for {projectName}</DialogTitle>
      <DialogContent>
        <Typography sx={{ color: "text.secondary", fontSize: "13px", mb: 1.5 }}>
          Only this project uses these changes. Later changes to the rig still reach the parts
          you haven&apos;t changed here.
        </Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {options && currentRig && (
          <RigPartsForm
            value={value}
            base={rig.base_parts}
            onChange={setValue}
            options={options}
            partSources={[currentRig, ...rig.setups.map((setup) => setup.parts)]}
          />
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>Cancel</Button>
        <Button variant="contained" onClick={save} disabled={saving || !options || !currentRig}>
          {saving ? "Saving…" : "Save for this project"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
