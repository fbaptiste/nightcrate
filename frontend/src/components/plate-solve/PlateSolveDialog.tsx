import { useCallback, useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Alert from "@mui/material/Alert";
import FormControl from "@mui/material/FormControl";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";

import { plateSolve, type PlateSolveResult } from "@/api/plateSolve";
import { useSettingsStore } from "@/stores/settingsStore";
import { monoFontFamily } from "@/theme/theme";

interface Props {
  open: boolean;
  onClose: () => void;
  imagePath: string;
  hdu: number;
  headerRa: number | null;
  headerDec: number | null;
}

type SolveMode = "auto" | "near" | "blind";

export function PlateSolveDialog({
  open,
  onClose,
  imagePath,
  hdu,
  headerRa,
  headerDec,
}: Props) {
  const { settings } = useSettingsStore();
  const [mode, setMode] = useState<SolveMode>("auto");
  const [solving, setSolving] = useState(false);
  const [result, setResult] = useState<PlateSolveResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef(false);

  const configured = !!settings?.astap_executable_path;

  useEffect(() => {
    if (open) {
      setResult(null);
      setError(null);
      setElapsed(0);
      setSolving(false);
      abortRef.current = false;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [open]);

  const handleSolve = useCallback(async () => {
    setSolving(true);
    setResult(null);
    setError(null);
    setElapsed(0);
    abortRef.current = false;

    const start = Date.now();
    timerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);

    try {
      const res = await plateSolve({
        image_path: imagePath,
        hdu,
        mode,
        timeout: mode === "blind" ? 300 : 180,
      });
      if (!abortRef.current) setResult(res);
    } catch (err: unknown) {
      if (!abortRef.current) {
        const msg = err instanceof Error ? err.message : String(err);
        try {
          const parsed = JSON.parse(msg);
          setError(parsed.detail || msg);
        } catch {
          setError(msg);
        }
      }
    } finally {
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
      setSolving(false);
    }
  }, [imagePath, hdu, mode]);

  const handleCopy = useCallback(() => {
    if (!result || !result.solved) return;
    const lines = [
      `RA: ${result.ra_hms} (${result.ra_deg}°)`,
      `Dec: ${result.dec_dms} (${result.dec_deg}°)`,
      `Pixel scale: ${result.pixel_scale_arcsec} arcsec/px`,
      `Rotation: ${result.rotation_deg}°`,
      result.fov_width_arcmin && result.fov_height_arcmin
        ? `FOV: ${result.fov_width_arcmin}′ × ${result.fov_height_arcmin}′`
        : null,
    ].filter(Boolean);
    navigator.clipboard.writeText(lines.join("\n"));
  }, [result]);

  const hasHints = headerRa !== null && headerDec !== null;

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ pb: 1 }}>Plate Solve</DialogTitle>
      <DialogContent dividers>
        {!configured ? (
          <Alert severity="info" sx={{ mb: 1 }}>
            ASTAP executable path is not configured. Set it in Settings before plate solving.
          </Alert>
        ) : result?.solved ? (
          <SolveResults result={result} onCopy={handleCopy} />
        ) : result && !result.solved ? (
          <Stack spacing={1.5}>
            <Alert severity="warning">
              {result.error_message || "Plate solve failed."}
            </Alert>
            {result.warning && (
              <Typography variant="body2" color="text.secondary">
                Warning: {result.warning}
              </Typography>
            )}
            {result.solve_time_seconds != null && (
              <Typography variant="caption" color="text.secondary">
                Completed in {result.solve_time_seconds}s
              </Typography>
            )}
          </Stack>
        ) : error ? (
          <Alert severity="error">{error}</Alert>
        ) : solving ? (
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 3, gap: 1.5 }}>
            <CircularProgress size={36} />
            <Typography variant="body2" color="text.secondary">
              Solving{mode === "blind" ? " (blind)" : ""}... {elapsed}s
            </Typography>
          </Box>
        ) : (
          <Stack spacing={2}>
            <Box>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                Solve mode
              </Typography>
              <FormControl size="small" fullWidth>
                <Select
                  value={mode}
                  onChange={(e) => setMode(e.target.value as SolveMode)}
                >
                  <MenuItem value="auto">
                    Auto {hasHints ? "(near solve — header hints available)" : "(blind solve — no hints)"}
                  </MenuItem>
                  <MenuItem value="near">Near solve (use coordinate hints)</MenuItem>
                  <MenuItem value="blind">Blind solve (search entire sky)</MenuItem>
                </Select>
              </FormControl>
            </Box>

            {hasHints && (
              <Box>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                  Coordinate hints from header
                </Typography>
                <Stack direction="row" spacing={2}>
                  <TextField
                    size="small"
                    label={"RA (°)"}
                    value={headerRa?.toFixed(4) ?? ""}
                    slotProps={{ input: { readOnly: true } }}
                    sx={{ flex: 1 }}
                  />
                  <TextField
                    size="small"
                    label={"Dec (°)"}
                    value={headerDec?.toFixed(4) ?? ""}
                    slotProps={{ input: { readOnly: true } }}
                    sx={{ flex: 1 }}
                  />
                </Stack>
              </Box>
            )}

            {!hasHints && mode === "near" && (
              <Alert severity="info" variant="outlined">
                No RA/Dec found in the image header. Near solve may fail without
                coordinate hints. Consider using Auto or Blind mode.
              </Alert>
            )}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} size="small">
          {result ? "Close" : "Cancel"}
        </Button>
        {configured && !solving && !result && (
          <Button variant="contained" size="small" onClick={handleSolve}>
            Solve
          </Button>
        )}
        {result && !result.solved && configured && (
          <Button variant="contained" size="small" onClick={() => { setResult(null); setError(null); }}>
            Retry
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}


function SolveResults({ result, onCopy }: { result: PlateSolveResult; onCopy: () => void }) {
  const rows: Array<{ label: string; value: string }> = [];

  if (result.ra_hms && result.ra_deg != null) {
    rows.push({ label: "RA", value: `${result.ra_hms}  (${result.ra_deg.toFixed(4)}°)` });
  }
  if (result.dec_dms && result.dec_deg != null) {
    rows.push({ label: "Dec", value: `${result.dec_dms}  (${result.dec_deg.toFixed(4)}°)` });
  }
  if (result.pixel_scale_arcsec != null) {
    rows.push({ label: "Pixel scale", value: `${result.pixel_scale_arcsec.toFixed(3)} arcsec/px` });
  }
  if (result.rotation_deg != null) {
    rows.push({ label: "Rotation", value: `${result.rotation_deg.toFixed(3)}°` });
  }
  if (result.fov_width_arcmin != null && result.fov_height_arcmin != null) {
    rows.push({
      label: "Field of view",
      value: `${result.fov_width_arcmin.toFixed(1)}′ × ${result.fov_height_arcmin.toFixed(1)}′`,
    });
  }
  if (result.image_width != null && result.image_height != null) {
    rows.push({ label: "Image size", value: `${result.image_width} × ${result.image_height} px` });
  }

  return (
    <Stack spacing={1.5}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Alert severity="info" sx={{ flex: 1, py: 0.25 }}>
          Solved{result.solve_time_seconds != null ? ` in ${result.solve_time_seconds}s` : ""}
        </Alert>
        <Tooltip title="Copy results" arrow>
          <IconButton size="small" onClick={onCopy} sx={{ ml: 1 }}>
            <ContentCopyIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      <Box
        component="table"
        sx={{
          width: "100%",
          borderCollapse: "collapse",
          "& td": { py: 0.5, px: 1, fontSize: "0.85rem" },
          "& td:first-of-type": {
            color: "text.secondary",
            fontWeight: 500,
            whiteSpace: "nowrap",
            width: "1%",
          },
          "& td:last-of-type": {
            fontFamily: monoFontFamily,
          },
        }}
      >
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <td>{r.label}</td>
              <td>{r.value}</td>
            </tr>
          ))}
        </tbody>
      </Box>

      {result.warning && (
        <Typography variant="caption" color="text.secondary">
          Warning: {result.warning}
        </Typography>
      )}
    </Stack>
  );
}
