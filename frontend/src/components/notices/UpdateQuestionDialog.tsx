import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Typography from "@mui/material/Typography";

export function UpdateQuestionDialog({ open, onAnswer, onDismiss }: { open: boolean; onAnswer: (answer: boolean) => void; onDismiss: () => void }) {
  return <Dialog open={open} onClose={onDismiss} maxWidth="sm" fullWidth>
    <DialogTitle>Check for new versions automatically?</DialogTitle>
    <DialogContent>
      <Typography>Once a day, NightCrate can ask GitHub whether a newer version of NightCrate or of the OpenNGC catalog exists. It sends nothing about your images or workspaces. If there is one, NightCrate tells you and asks before installing anything.</Typography>
      <Typography color="text.secondary" sx={{ fontSize: 13, mt: 1.5 }}>You can change this later in Admin.</Typography>
    </DialogContent>
    <DialogActions>
      <Button sx={{ color: "text.secondary" }} onClick={() => onAnswer(false)}>Don't check</Button>
      <Button
        variant="contained"
        autoFocus
        disableFocusRipple
        sx={{ "&.Mui-focusVisible": { outline: "2px solid", outlineColor: "primary.main", outlineOffset: "2px" } }}
        onClick={() => onAnswer(true)}
      >Check daily</Button>
    </DialogActions>
  </Dialog>;
}
