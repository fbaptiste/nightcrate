import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import { deleteNightNote, saveNightNote } from "@/api/projectSessions";
import { formatNight } from "@/lib/localDate";

interface Props {
  projectId: number;
  night: string;
  note: string | null;
  open: boolean;
  onClose: () => void;
}

export default function NightNoteDialog({ projectId, night, note, open, onClose }: Props) {
  const queryClient = useQueryClient();
  const [text, setText] = useState(note ?? "");

  const finish = () => {
    queryClient.invalidateQueries({ queryKey: ["project-night-notes", projectId] });
    onClose();
  };
  const saveMut = useMutation({
    mutationFn: async () => {
      const trimmed = text.trim();
      if (trimmed) await saveNightNote(projectId, night, trimmed);
      else await deleteNightNote(projectId, night);
    },
    onSuccess: finish,
  });
  const deleteMut = useMutation({
    mutationFn: () => deleteNightNote(projectId, night),
    onSuccess: finish,
  });
  const error = saveMut.error ?? deleteMut.error;
  const pending = saveMut.isPending || deleteMut.isPending;
  const handleSave = () => {
    if (!text.trim() && note == null) {
      onClose();
      return;
    }
    saveMut.mutate();
  };

  return (
    <Dialog open={open} onClose={pending ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle>Note for {formatNight(night)}</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          fullWidth
          multiline
          minRows={3}
          value={text}
          onChange={(event) => setText(event.target.value)}
          inputProps={{ maxLength: 10000 }}
          error={error != null}
          helperText={error ? String(error) : undefined}
          sx={{ mt: 0.5 }}
        />
      </DialogContent>
      <DialogActions>
        {note != null && (
          <Button color="error" onClick={() => deleteMut.mutate()} disabled={pending} sx={{ mr: "auto" }}>
            Delete
          </Button>
        )}
        <Button onClick={onClose} disabled={pending}>Cancel</Button>
        <Button variant="contained" onClick={handleSave} disabled={pending}>
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}
