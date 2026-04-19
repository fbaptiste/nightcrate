import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type { HorizonPoint } from "./HorizonChart";

interface Props {
  anchorEl: HTMLElement | null;
  point: HorizonPoint | null;
  pointIndex: number | null;
  onCommit: (index: number, az: number, alt: number) => void;
  onDelete: (index: number) => void;
  onClose: () => void;
}

/**
 * Small popover for precision-editing a single horizon point.
 * Triggered by a double-click on a point marker in the editor.
 */
export default function HorizonPointEditPopover({
  anchorEl,
  point,
  pointIndex,
  onCommit,
  onDelete,
  onClose,
}: Props) {
  const [azStr, setAzStr] = useState("");
  const [altStr, setAltStr] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (point) {
      setAzStr(point.azimuth_deg.toFixed(2));
      setAltStr(point.altitude_deg.toFixed(2));
      setError(null);
    }
  }, [point]);

  const handleCommit = () => {
    if (pointIndex === null) return;
    const az = parseFloat(azStr);
    const alt = parseFloat(altStr);
    if (!Number.isFinite(az) || !Number.isFinite(alt)) {
      setError("Enter valid numbers.");
      return;
    }
    if (az < 0 || az >= 360) {
      setError("Azimuth must be in [0, 360).");
      return;
    }
    if (alt < -5 || alt > 90) {
      setError("Altitude must be in [-5, 90].");
      return;
    }
    onCommit(pointIndex, az, alt);
    onClose();
  };

  const open = anchorEl !== null && point !== null && pointIndex !== null;

  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: "top", horizontal: "center" }}
      transformOrigin={{ vertical: "bottom", horizontal: "center" }}
    >
      <Box sx={{ p: 2, minWidth: 240 }}>
        <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
          Edit point
        </Typography>
        <Stack spacing={1.5}>
          <TextField
            size="small"
            label={"Azimuth (\u00B0)"}
            value={azStr}
            onChange={(e) => setAzStr(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCommit();
              if (e.key === "Escape") onClose();
            }}
            autoFocus
            inputProps={{ inputMode: "decimal" }}
          />
          <TextField
            size="small"
            label={"Altitude (\u00B0)"}
            value={altStr}
            onChange={(e) => setAltStr(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCommit();
              if (e.key === "Escape") onClose();
            }}
            inputProps={{ inputMode: "decimal" }}
          />
          {error && (
            <Typography variant="caption" color="warning.main">
              {error}
            </Typography>
          )}
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              color="warning"
              onClick={() => {
                if (pointIndex !== null) {
                  onDelete(pointIndex);
                  onClose();
                }
              }}
            >
              Delete
            </Button>
            <Box sx={{ flex: 1 }} />
            <Button size="small" onClick={onClose}>
              Cancel
            </Button>
            <Button size="small" variant="contained" onClick={handleCommit}>
              Save
            </Button>
          </Stack>
        </Stack>
      </Box>
    </Popover>
  );
}
