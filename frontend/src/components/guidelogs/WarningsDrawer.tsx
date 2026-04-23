/**
 * Parse-time warnings drawer.
 *
 * Chip in the page header shows the count; click expands to a short
 * list. v0.22.0 keeps it simple — Pass B reshapes this as a grouped
 * tabs/drawer when analysis-time warnings (settle detection, FFT
 * cadence, etc.) land.
 */
import { useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import type { ParseWarning } from "@/api/guideLogs";

interface Props {
  warnings: ParseWarning[];
}

export default function WarningsDrawer({ warnings }: Props) {
  const [open, setOpen] = useState(false);
  if (warnings.length === 0) return null;

  return (
    <Box>
      <Chip
        icon={<WarningAmberIcon />}
        label={`${warnings.length} warning${warnings.length === 1 ? "" : "s"}`}
        color="warning"
        variant={open ? "filled" : "outlined"}
        onClick={() => setOpen((v) => !v)}
        size="small"
      />
      <Collapse in={open}>
        <Stack spacing={0.5} sx={{ mt: 1, pl: 1, borderLeft: 2, borderColor: "warning.main" }}>
          {warnings.map((w, i) => (
            <Box key={i}>
              <Typography variant="caption" sx={{ fontFamily: "monospace", fontWeight: 600 }}>
                {w.code}
                {w.section_index !== null ? ` (section ${w.section_index})` : ""}
              </Typography>
              <Typography variant="body2" sx={{ color: "text.secondary" }}>
                {w.message}
              </Typography>
            </Box>
          ))}
        </Stack>
      </Collapse>
    </Box>
  );
}
