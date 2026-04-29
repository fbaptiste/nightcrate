import { useCallback, useEffect, useRef, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Alert from "@mui/material/Alert";
import Checkbox from "@mui/material/Checkbox";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";

import { plateSolve, fetchSolveProgress, fetchExtractPreview, cancelSolve, type PlateSolveResult } from "@/api/plateSolve";
import { fetchDsos, type DsoListItem } from "@/api/dsos";
import { useSettingsStore } from "@/stores/settingsStore";
import { monoFontFamily } from "@/theme/theme";

interface Props {
  open: boolean;
  onClose: () => void;
  imagePath: string;
  hdu: number;
  headerRa: number | null;
  headerDec: number | null;
  onSolved?: (result: PlateSolveResult) => void;
}

type SolveMode = "auto" | "near" | "blind" | "extract";

export function PlateSolveDialog({
  open,
  onClose,
  imagePath,
  hdu,
  headerRa,
  headerDec,
  onSolved,
}: Props) {
  const { settings } = useSettingsStore();
  const [mode, setMode] = useState<SolveMode>("auto");
  const [targetInput, setTargetInput] = useState("");
  const [targetOptions, setTargetOptions] = useState<DsoListItem[]>([]);
  const [selectedTarget, setSelectedTarget] = useState<DsoListItem | null>(null);
  const [searching, setSearching] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [solving, setSolving] = useState(false);
  const [result, setResult] = useState<PlateSolveResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [progressMsg, setProgressMsg] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [extractThresh, setExtractThresh] = useState(5);
  const [extractMinArea, setExtractMinArea] = useState(5);
  const [extractRoundness, setExtractRoundness] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef(false);

  const configured = !!settings?.astap_executable_path;

  useEffect(() => {
    if (open) {
      setResult(null);
      setError(null);
      setElapsed(0);
      setProgressMsg("");
      setSolving(false);
      setTargetInput("");
      setTargetOptions([]);
      setSelectedTarget(null);
      if (previewUrl) { URL.revokeObjectURL(previewUrl); setPreviewUrl(null); }
      setPreviewing(false);
      abortRef.current = false;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (progressRef.current) clearInterval(progressRef.current);
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [open]);

  const handleTargetSearch = useCallback((query: string) => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!query.trim() || query.trim().length < 2) {
      setTargetOptions([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    searchTimer.current = setTimeout(async () => {
      try {
        const result = await fetchDsos({ q: query.trim(), limit: 10 });
        setTargetOptions(result.items);
      } catch {
        setTargetOptions([]);
      } finally {
        setSearching(false);
      }
    }, 300);
  }, []);

  const handleCancel = useCallback(() => {
    abortRef.current = true;
    cancelSolve().catch(() => {});
    if (timerRef.current) clearInterval(timerRef.current);
    if (progressRef.current) clearInterval(progressRef.current);
    timerRef.current = null;
    progressRef.current = null;
    setSolving(false);
    setProgressMsg("");
  }, []);

  const handlePreview = useCallback(async () => {
    setPreviewing(true);
    setError(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    try {
      const url = await fetchExtractPreview(imagePath, hdu, {
        thresh: extractThresh,
        minArea: extractMinArea,
        maxElongation: extractRoundness ? 1.5 : 0,
      });
      setPreviewUrl(url);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewing(false);
    }
  }, [imagePath, hdu, previewUrl, extractThresh, extractMinArea, extractRoundness]);

  const handleSolve = useCallback(async () => {
    setSolving(true);
    setResult(null);
    setError(null);
    setElapsed(0);
    setProgressMsg("Starting ASTAP...");
    abortRef.current = false;

    const start = Date.now();
    timerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    const pollProgress = async () => {
      try {
        const p = await fetchSolveProgress();
        if (p.message && !abortRef.current) setProgressMsg(p.message);
      } catch { /* ignore */ }
    };
    pollProgress();
    progressRef.current = setInterval(pollProgress, 1000);

    try {
      const effectiveRa = selectedTarget?.ra_deg ?? headerRa ?? undefined;
      const effectiveDec = selectedTarget?.dec_deg ?? headerDec ?? undefined;
      const res = await plateSolve({
        image_path: imagePath,
        hdu,
        mode,
        ra_hint: effectiveRa,
        dec_hint: effectiveDec,
        timeout: mode === "blind" ? 300 : 180,
        ...(mode === "extract" ? {
          extract_thresh: extractThresh,
          extract_min_area: extractMinArea,
          extract_max_elongation: extractRoundness ? 1.5 : 0,
        } : {}),
      });
      if (!abortRef.current) {
        setResult(res);
        if (res.solved && onSolved) onSolved(res);
      }
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
      if (progressRef.current) clearInterval(progressRef.current);
      timerRef.current = null;
      progressRef.current = null;
      setSolving(false);
      setProgressMsg("");
    }
  }, [imagePath, hdu, mode, selectedTarget, headerRa, headerDec]);

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

  const hasHeaderHints = headerRa !== null && headerDec !== null;
  const hasHints = hasHeaderHints || selectedTarget != null;

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth={previewUrl ? "md" : "sm"}>
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
            {progressMsg && (
              <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 400, textAlign: "center", wordBreak: "break-word" }}>
                {progressMsg}
              </Typography>
            )}
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
                  onChange={(e) => {
                    setMode(e.target.value as SolveMode);
                    if (previewUrl) { URL.revokeObjectURL(previewUrl); setPreviewUrl(null); }
                  }}
                >
                  <MenuItem value="auto">
                    Auto {hasHints ? "(near solve — hints available)" : "(blind solve — no hints)"}
                  </MenuItem>
                  <MenuItem value="near">Near solve (use coordinate hints)</MenuItem>
                  <MenuItem value="blind">Blind solve (search entire sky)</MenuItem>
                  <MenuItem value="extract">Extract stars &amp; solve (for stretched images)</MenuItem>
                </Select>
              </FormControl>
            </Box>

            <Box>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                Target (for coordinate hints)
              </Typography>
              <Autocomplete
                size="small"
                freeSolo
                options={targetOptions}
                getOptionLabel={(opt) =>
                  typeof opt === "string"
                    ? opt
                    : opt.common_name
                      ? `${opt.primary_designation} — ${opt.common_name}`
                      : opt.primary_designation
                }
                filterOptions={(x) => x}
                inputValue={targetInput}
                onInputChange={(_, value, reason) => {
                  if (reason !== "reset") {
                    setTargetInput(value);
                    handleTargetSearch(value);
                  }
                }}
                onChange={(_, value) => {
                  if (value && typeof value !== "string") {
                    setSelectedTarget(value);
                    setTargetInput(
                      value.common_name
                        ? `${value.primary_designation} — ${value.common_name}`
                        : value.primary_designation,
                    );
                  } else {
                    setSelectedTarget(null);
                  }
                }}
                loading={searching}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    placeholder="e.g. NGC 4565, M42, Orion"
                    slotProps={{
                      input: {
                        ...params.InputProps,
                        endAdornment: (
                          <>
                            {searching && <CircularProgress size={16} />}
                            {params.InputProps.endAdornment}
                          </>
                        ),
                      },
                    }}
                  />
                )}
                renderOption={(props, option) => (
                  <li {...props} key={option.id}>
                    <Box>
                      <Typography sx={{ fontSize: "0.85rem" }}>
                        {option.primary_designation}
                        {option.common_name && (
                          <Typography component="span" color="text.secondary" sx={{ ml: 0.5, fontSize: "0.8rem" }}>
                            {option.common_name}
                          </Typography>
                        )}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {option.obj_type} · RA {option.ra_deg?.toFixed(2)}° Dec {option.dec_deg?.toFixed(2)}°
                      </Typography>
                    </Box>
                  </li>
                )}
              />
              {selectedTarget && (
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: "block" }}>
                  RA {selectedTarget.ra_deg?.toFixed(4)}° Dec {selectedTarget.dec_deg?.toFixed(4)}°
                </Typography>
              )}
            </Box>

            {hasHeaderHints && (
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

            {mode === "extract" && (
              <Box sx={{ bgcolor: "action.hover", borderRadius: 1, p: 1.5 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Extraction settings
                </Typography>
                <Stack spacing={1.5}>
                  <Box>
                    <Typography variant="caption">
                      Detection threshold: {extractThresh}σ
                    </Typography>
                    <Slider
                      size="small"
                      value={extractThresh}
                      onChange={(_, v) => setExtractThresh(v as number)}
                      onChangeCommitted={() => { if (previewUrl) handlePreview(); }}
                      min={2}
                      max={50}
                      step={1}
                      valueLabelDisplay="auto"
                    />
                  </Box>
                  <Box>
                    <Typography variant="caption">
                      Min area: {extractMinArea} px
                    </Typography>
                    <Slider
                      size="small"
                      value={extractMinArea}
                      onChange={(_, v) => setExtractMinArea(v as number)}
                      onChangeCommitted={() => { if (previewUrl) handlePreview(); }}
                      min={1}
                      max={50}
                      step={1}
                      valueLabelDisplay="auto"
                    />
                  </Box>
                  <FormControlLabel
                    control={
                      <Checkbox
                        size="small"
                        checked={extractRoundness}
                        onChange={(_, checked) => { setExtractRoundness(checked); if (previewUrl) setTimeout(() => handlePreview(), 0); }}
                      />
                    }
                    label={
                      <Typography variant="caption">
                        Roundness filter (reject elongated detections)
                      </Typography>
                    }
                  />
                </Stack>
              </Box>
            )}

            {!hasHints && mode === "near" && (
              <Alert severity="info" variant="outlined">
                No coordinate hints available. Enter a target name above, or use Auto / Blind mode.
              </Alert>
            )}

            {/* Extract mode preview */}
            {mode === "extract" && previewing && (
              <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
                <CircularProgress size={36} />
                <Typography variant="body2" color="text.secondary" sx={{ ml: 2, alignSelf: "center" }}>
                  Extracting stars...
                </Typography>
              </Box>
            )}
            {mode === "extract" && previewUrl && (
              <Box sx={{ mt: 1 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                  Star map preview — this image will be sent to ASTAP
                </Typography>
                <Box
                  component="img"
                  src={previewUrl}
                  alt="Star map preview"
                  sx={{
                    width: "100%",
                    maxHeight: 500,
                    objectFit: "contain",
                    borderRadius: 1,
                    bgcolor: "#000000",
                  }}
                />
              </Box>
            )}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={solving ? () => { handleCancel(); onClose(); } : onClose} size="small">
          {result ? "Close" : "Cancel"}
        </Button>
        {configured && !solving && !result && mode === "extract" && !previewUrl && (
          <Button variant="contained" size="small" onClick={handlePreview} disabled={previewing}>
            {previewing ? "Extracting..." : "Preview"}
          </Button>
        )}
        {configured && !solving && !result && (mode !== "extract" || previewUrl) && (
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
