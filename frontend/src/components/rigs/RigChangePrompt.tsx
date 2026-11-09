import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import type { RigChangeChoiceDetail } from "@/api/rigs";

interface RigChangePromptProps {
  open: boolean;
  detail: RigChangeChoiceDetail;
  saving: boolean;
  onChoose: (mode: "existing" | "from_now_on") => void;
  onCancel: () => void;
}

const GROUP_LABELS: Record<string, string> = {
  telescope: "Telescope",
  camera: "Camera",
  filters: "Filters",
  mount: "Mount",
  focuser: "Focuser",
  guider: "Guiding",
  guide_camera: "Guide camera",
  computer: "Computer",
  software: "Software",
};

function countLabel(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

function ChoiceButton({
  title,
  description,
  onClick,
  disabled,
}: {
  title: string;
  description: string;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <Button
      variant="outlined"
      onClick={onClick}
      disabled={disabled}
      sx={(theme) => ({
        width: "100%",
        display: "grid",
        gridTemplateColumns: "1fr auto",
        alignItems: "center",
        gap: "4px 16px",
        textAlign: "left",
        p: "12px 14px",
        borderRadius: "8px",
        borderColor: theme.palette.mode === "dark" ? "rgba(255, 255, 255, 0.23)" : "#c4c1bb",
        color: "text.primary",
        textTransform: "none",
        "&:hover": {
          borderColor: theme.palette.mode === "dark" ? "#d4993f" : "#c07b2b",
          bgcolor: theme.palette.mode === "dark" ? "#d4993f0f" : "#c07b2b0f",
        },
      })}
    >
      <Typography sx={{ gridColumn: 1, fontSize: "15px", lineHeight: "20px", fontWeight: 600 }}>
        {title}
      </Typography>
      <Typography
        sx={{ gridColumn: 1, fontSize: "13px", lineHeight: "18px", color: "text.secondary" }}
      >
        {description}
      </Typography>
      <Typography
        aria-hidden="true"
        sx={(theme) => ({
          gridColumn: 2,
          gridRow: "1 / span 2",
          fontSize: "18px",
          lineHeight: "22px",
          color: theme.palette.mode === "dark" ? "#d4993f" : "#c07b2b",
        })}
      >
        {"›"}
      </Typography>
    </Button>
  );
}

export default function RigChangePrompt({
  open,
  detail,
  saving,
  onChoose,
  onCancel,
}: RigChangePromptProps) {
  const projects = countLabel(detail.project_count, "project", "projects");
  const nights = countLabel(detail.night_count, "night", "nights");

  return (
    <Dialog open={open} onClose={saving ? undefined : onCancel} maxWidth="sm" fullWidth>
      <DialogTitle>
        This rig has been used on {projects} ({nights})
      </DialogTitle>
      <DialogContent>
        <Box
          component="dl"
          sx={(theme) => ({
            display: "grid",
            gridTemplateColumns: "90px 1fr",
            gap: "2px 12px",
            m: 0,
            mb: 2,
            p: "10px 12px",
            borderRadius: "6px",
            bgcolor: theme.palette.mode === "dark" ? "#1a1c20" : "#f5f4f2",
            fontSize: "13px",
            lineHeight: "18px",
          })}
        >
          {detail.changes.map((change) => (
            <Box key={change.group} sx={{ display: "contents" }}>
              <Box component="dt" sx={{ color: "text.secondary" }}>
                {GROUP_LABELS[change.group] ?? change.group}
              </Box>
              <Box component="dd" sx={{ m: 0 }}>
                {change.before} {"→"} {change.after}
              </Box>
            </Box>
          ))}
        </Box>
        <Typography sx={{ mb: 1.5 }}>
          Apply the change to them too, or only from now on?
        </Typography>
        <Box sx={{ display: "grid", gap: "10px" }}>
          <ChoiceButton
            title="Apply to existing projects"
            description={`For a mistake: the ${projects} ${
              detail.project_count === 1 ? "changes" : "change"
            } too.`}
            onClick={() => onChoose("existing")}
            disabled={saving}
          />
          <ChoiceButton
            title="From now on"
            description="For a real change: existing projects keep the old setup."
            onClick={() => onChoose("from_now_on")}
            disabled={saving}
          />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={saving}>Cancel</Button>
      </DialogActions>
    </Dialog>
  );
}
