import { useState, type MouseEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import ArrowDropDownIcon from "@mui/icons-material/ArrowDropDown";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Typography from "@mui/material/Typography";
import {
  updateProject,
  type Project,
  type ProjectStatus,
} from "@/api/projects";

interface Props {
  project: Project;
  onUpdated: (project: Project) => void;
  onError: (message: string) => void;
}

const STATUSES: Array<{
  value: ProjectStatus;
  label: string;
  description: string;
}> = [
  { value: "active", label: "Active", description: "Still capturing" },
  { value: "paused", label: "Paused", description: "On hold" },
  { value: "complete", label: "Complete", description: "Finished" },
  { value: "abandoned", label: "Abandoned", description: "Stopped for good" },
];

export default function ProjectStatusChip({ project, onUpdated, onError }: Props) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const mutation = useMutation({
    mutationFn: (status: ProjectStatus) => updateProject(project.id, { status }),
    onSuccess: onUpdated,
    onError: (error) => {
      const message = error instanceof Error ? error.message : String(error);
      onError(`Couldn't change the status: ${message}`);
    },
  });

  const openMenu = (event: MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const choose = (status: ProjectStatus) => {
    setAnchorEl(null);
    if (status !== project.status) mutation.mutate(status);
  };

  const current = STATUSES.find((status) => status.value === project.status);

  return (
    <>
      <ButtonBase
        onClick={openMenu}
        disabled={mutation.isPending}
        aria-haspopup="listbox"
        aria-expanded={anchorEl ? true : undefined}
        title="Change status"
        sx={(theme) => ({
          ml: "100px",
          height: "26px",
          pl: "12px",
          pr: "6px",
          borderRadius: "13px",
          gap: "2px",
          bgcolor: theme.palette.mode === "dark" ? "#31343a" : "#ebe8e3",
          fontSize: "13px",
          "&:hover": {
            bgcolor: theme.palette.mode === "dark" ? "#4d4e51" : "#c5c3bf",
          },
        })}
      >
        {current?.label ?? project.status}
        <ArrowDropDownIcon sx={{ fontSize: "16px", color: "text.secondary" }} />
      </ButtonBase>
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        MenuListProps={{
          "aria-label": "Status",
          role: "listbox",
          sx: { py: "6px" },
        }}
        slotProps={{
          paper: {
            sx: {
              width: "260px",
              borderRadius: "6px",
              border: 1,
              borderColor: "divider",
              boxShadow: "0 6px 24px rgba(0, 0, 0, 0.28)",
            },
          },
        }}
      >
        {STATUSES.map((status) => (
          <MenuItem
            key={status.value}
            selected={status.value === project.status}
            onClick={() => choose(status.value)}
            role="option"
            sx={{ px: "14px", py: "7px" }}
          >
            <Box>
              <Typography sx={{ fontSize: "14px", fontWeight: 500 }}>
                {status.label}
              </Typography>
              <Typography sx={{ fontSize: "12px", color: "text.secondary" }}>
                {status.description}
              </Typography>
            </Box>
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
