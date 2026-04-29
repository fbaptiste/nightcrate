import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";

import {
  plateSolve,
  fetchSolveProgress,
  validateReferenceImage,
  cancelSolve,
  type PlateSolveResult,
} from "@/api/plateSolve";
import { FileBrowser } from "@/components/fits/FileBrowser";
import { fetchDsos, type DsoListItem } from "@/api/dsos";
import {
  fetchRigs,
  fetchEquipmentOptions,
  type Rig,
  type TelescopeConfigOption,
  type CameraOption,
} from "@/api/rigs";
import { useSettingsStore } from "@/stores/settingsStore";
import { monoFontFamily } from "@/theme/theme";

interface Props {
  open: boolean;
  onClose: () => void;
  imagePath: string;
  hdu: number;
  headerRa: number | null;
  headerDec: number | null;
  headerFocalLength: number | null;
  headerPixelSize: number | null;
  headerBinning: number | null;
  onSolved?: (result: PlateSolveResult) => void;
}

type EquipmentMode = "rig" | "equipment" | "manual";

const BINNING_OPTIONS = [1, 2, 3, 4];

function computeFovDeg(
  focalLengthMm: number,
  pixelSizeUm: number,
  binning: number,
  resolutionY: number | null,
): { pixelScale: number; fovH: number | null } {
  const ps = ((pixelSizeUm * binning) / focalLengthMm) * 206.265;
  return {
    pixelScale: ps,
    fovH: resolutionY != null ? (ps * resolutionY) / 3600 : null,
  };
}

export function PlateSolveDialog({
  open,
  onClose,
  imagePath,
  hdu,
  headerRa,
  headerDec,
  headerFocalLength,
  headerPixelSize,
  headerBinning,
  onSolved,
}: Props) {
  const { settings } = useSettingsStore();

  // ── Tab state ──
  const [activeTab, setActiveTab] = useState(0);

  // ── Target / coordinate hints ──
  const [targetInput, setTargetInput] = useState("");
  const [targetOptions, setTargetOptions] = useState<DsoListItem[]>([]);
  const [selectedTarget, setSelectedTarget] = useState<DsoListItem | null>(null);
  const [searching, setSearching] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Equipment hints ──
  const [equipmentMode, setEquipmentMode] = useState<EquipmentMode | null>(null);
  const [selectedRigId, setSelectedRigId] = useState<number | null>(null);
  const [selectedConfigId, setSelectedConfigId] = useState<number | null>(null);
  const [selectedCameraId, setSelectedCameraId] = useState<number | null>(null);
  const [focalLength, setFocalLength] = useState<string>("");
  const [pixelSize, setPixelSize] = useState<string>("");
  const [binning, setBinning] = useState(1);

  // ── Reference image (tab 2) ──
  const [referencePath, setReferencePath] = useState("");
  const [referenceValidation, setReferenceValidation] = useState<{
    valid: boolean;
    error?: string;
    width?: number;
    height?: number;
  } | null>(null);
  const [referenceValidating, setReferenceValidating] = useState(false);
  const [referenceBrowserOpen, setReferenceBrowserOpen] = useState(false);

  // ── Solve state ──
  const [solving, setSolving] = useState(false);
  const [result, setResult] = useState<PlateSolveResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [progressMsg, setProgressMsg] = useState("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef(false);

  const configured = !!settings?.astap_executable_path;

  // ── Data queries ──
  const rigsQuery = useQuery({
    queryKey: ["rigs"],
    queryFn: () => fetchRigs(),
    enabled: open && equipmentMode === "rig",
    staleTime: 60_000,
  });
  const equipQuery = useQuery({
    queryKey: ["equipmentOptions"],
    queryFn: fetchEquipmentOptions,
    enabled: open && equipmentMode === "equipment",
    staleTime: 60_000,
  });

  // ── Derived equipment values ──
  const selectedRig: Rig | undefined = useMemo(
    () => rigsQuery.data?.find((r) => r.id === selectedRigId),
    [rigsQuery.data, selectedRigId],
  );

  const selectedConfig: TelescopeConfigOption | undefined = useMemo(() => {
    if (!equipQuery.data || selectedConfigId == null) return undefined;
    for (const t of equipQuery.data.telescopes) {
      const c = t.configs.find((cfg) => cfg.id === selectedConfigId);
      if (c) return c;
    }
    return undefined;
  }, [equipQuery.data, selectedConfigId]);

  const selectedCamera: CameraOption | undefined = useMemo(
    () => equipQuery.data?.cameras.find((c) => c.id === selectedCameraId),
    [equipQuery.data, selectedCameraId],
  );

  const fovInfo = useMemo(() => {
    if (equipmentMode === "rig" && selectedRig) {
      const fl = selectedRig.effective_focal_length_mm;
      const ps = selectedRig.pixel_size_um;
      const resY = selectedRig.sensor_resolution_y;
      return computeFovDeg(fl, ps, binning, resY);
    }
    if (equipmentMode === "equipment" && selectedConfig && selectedCamera) {
      const fl = selectedConfig.effective_focal_length_mm;
      const ps = selectedCamera.pixel_size_um;
      const resY = selectedCamera.resolution_y;
      return computeFovDeg(fl, ps, binning, resY);
    }
    if (equipmentMode === "manual") {
      const fl = parseFloat(focalLength);
      const ps = parseFloat(pixelSize);
      if (fl > 0 && ps > 0) return computeFovDeg(fl, ps, binning, null);
    }
    return null;
  }, [equipmentMode, selectedRig, selectedConfig, selectedCamera, focalLength, pixelSize, binning]);

  // ── Reset on open ──
  useEffect(() => {
    if (open) {
      setActiveTab(0);
      setResult(null);
      setError(null);
      setElapsed(0);
      setProgressMsg("");
      setSolving(false);
      setTargetInput("");
      setTargetOptions([]);
      setSelectedTarget(null);
      setReferencePath("");
      setReferenceValidation(null);
      setReferenceValidating(false);
      abortRef.current = false;

      // Pre-fill equipment from headers
      if (headerFocalLength != null || headerPixelSize != null) {
        setEquipmentMode("manual");
        setFocalLength(headerFocalLength != null ? String(headerFocalLength) : "");
        setPixelSize(headerPixelSize != null ? String(headerPixelSize) : "");
        setBinning(headerBinning != null && headerBinning >= 1 ? headerBinning : 1);
      } else {
        setEquipmentMode(null);
        setFocalLength("");
        setPixelSize("");
        setBinning(1);
      }
      setSelectedRigId(null);
      setSelectedConfigId(null);
      setSelectedCameraId(null);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (progressRef.current) clearInterval(progressRef.current);
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [open]);

  // ── Coordinate state ──
  const effectiveRa = selectedTarget?.ra_deg ?? headerRa ?? undefined;
  const effectiveDec = selectedTarget?.dec_deg ?? headerDec ?? undefined;
  const hasCoordinates = effectiveRa != null && effectiveDec != null;
  const isBlind = !hasCoordinates;

  // ── Handlers ──
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
        const res = await fetchDsos({ q: query.trim(), limit: 10 });
        setTargetOptions(res.items);
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

  const handleReferenceSelect = useCallback(
    async (path: string) => {
      setReferencePath(path);
      setReferenceValidation(null);
      setReferenceValidating(true);
      try {
        const res = await validateReferenceImage(imagePath, hdu, path);
        setReferenceValidation(res);
      } catch (err: unknown) {
        setReferenceValidation({
          valid: false,
          error: err instanceof Error ? err.message : String(err),
        });
      } finally {
        setReferenceValidating(false);
      }
    },
    [imagePath, hdu],
  );

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
      } catch {
        /* ignore */
      }
    };
    pollProgress();
    progressRef.current = setInterval(pollProgress, 1000);

    try {
      const isReference = activeTab === 1;
      const solveImagePath = isReference ? referencePath : imagePath;
      const solveHdu = isReference ? 0 : hdu;
      const mode = hasCoordinates ? "near" : "blind";

      const res = await plateSolve({
        image_path: solveImagePath,
        hdu: solveHdu,
        mode,
        ra_hint: effectiveRa,
        dec_hint: effectiveDec,
        fov_hint: fovInfo?.fovH ?? undefined,
        timeout: isBlind ? 300 : 180,
      });
      if (!abortRef.current) {
        setResult(res);
        if (res.solved && onSolved) onSolved(res);
        if (res.solved) onClose();
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
  }, [
    activeTab,
    imagePath,
    hdu,
    referencePath,
    hasCoordinates,
    effectiveRa,
    effectiveDec,
    fovInfo?.fovH,
    isBlind,
    onSolved,
    onClose,
  ]);

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

  // ── Solve button enablement ──
  const canSolve =
    configured &&
    !solving &&
    !result &&
    (activeTab === 0 || referenceValidation?.valid === true);

  return (
    <>
      <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
        <DialogTitle sx={{ pb: 1 }}>Plate Solve</DialogTitle>
        <DialogContent dividers>
          {!configured ? (
            <Alert severity="info" sx={{ mb: 1 }}>
              ASTAP executable path is not configured. Set it in Settings before
              plate solving.
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
            <Box
              sx={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                py: 3,
                gap: 1.5,
              }}
            >
              <CircularProgress size={36} />
              <Typography variant="body2" color="text.secondary">
                Solving{isBlind ? " (blind)" : ""}... {elapsed}s
              </Typography>
              {progressMsg && (
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{
                    maxWidth: 400,
                    textAlign: "center",
                    wordBreak: "break-word",
                  }}
                >
                  {progressMsg}
                </Typography>
              )}
            </Box>
          ) : (
            <Stack spacing={2}>
              {/* ── Tabs ── */}
              <Tabs
                value={activeTab}
                onChange={(_, v) => setActiveTab(v)}
                variant="fullWidth"
                sx={{ minHeight: 36, "& .MuiTab-root": { minHeight: 36, py: 0.5, textTransform: "none" } }}
              >
                <Tab label="Solve" />
                <Tab label="From Reference Image" />
              </Tabs>

              {/* ── Reference image picker (tab 2 only) ── */}
              {activeTab === 1 && (
                <Box>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mb: 0.5 }}
                  >
                    Reference image (must match current image dimensions)
                  </Typography>
                  <Stack direction="row" gap={1} alignItems="center">
                    <TextField
                      size="small"
                      fullWidth
                      value={referencePath}
                      placeholder="Path to reference image..."
                      onChange={(e) => {
                        setReferencePath(e.target.value);
                        setReferenceValidation(null);
                      }}
                      inputProps={{
                        style: {
                          fontFamily: monoFontFamily,
                          fontSize: "0.75rem",
                        },
                      }}
                    />
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={() => setReferenceBrowserOpen(true)}
                      sx={{ height: 32, flexShrink: 0 }}
                    >
                      Browse
                    </Button>
                  </Stack>
                  {referenceValidating && (
                    <Stack
                      direction="row"
                      gap={1}
                      alignItems="center"
                      sx={{ mt: 0.5 }}
                    >
                      <CircularProgress size={14} />
                      <Typography variant="caption" color="text.secondary">
                        Validating dimensions...
                      </Typography>
                    </Stack>
                  )}
                  {referenceValidation?.valid && (
                    <Alert
                      severity="success"
                      sx={{ mt: 0.5 }}
                      variant="outlined"
                    >
                      Dimensions match ({referenceValidation.width}
                      {"×"}
                      {referenceValidation.height})
                    </Alert>
                  )}
                  {referenceValidation && !referenceValidation.valid && (
                    <Alert
                      severity="error"
                      sx={{ mt: 0.5 }}
                      variant="outlined"
                    >
                      {referenceValidation.error}
                    </Alert>
                  )}
                </Box>
              )}

              {/* ── Coordinate hints ── */}
              <Box>
                <Stack
                  direction="row"
                  alignItems="center"
                  gap={1}
                  sx={{ mb: 0.5 }}
                >
                  <Typography variant="body2" color="text.secondary">
                    Coordinate hints
                  </Typography>
                  {isBlind && (
                    <Chip
                      label="Blind Solve"
                      size="small"
                      color="warning"
                      variant="outlined"
                      sx={{ fontSize: "0.65rem", height: 20 }}
                    />
                  )}
                </Stack>
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
                      placeholder="Search target (e.g. NGC 4565, M42, Orion)..."
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
                            <Typography
                              component="span"
                              color="text.secondary"
                              sx={{ ml: 0.5, fontSize: "0.8rem" }}
                            >
                              {option.common_name}
                            </Typography>
                          )}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {option.obj_type} · RA{" "}
                          {option.ra_deg?.toFixed(2)}° Dec{" "}
                          {option.dec_deg?.toFixed(2)}°
                        </Typography>
                      </Box>
                    </li>
                  )}
                />
                {hasCoordinates && (
                  <Stack spacing={0.5} sx={{ mt: 1.5 }}>
                    <Typography variant="caption" color="text.secondary">
                      {selectedTarget ? "From target" : "From image header"}
                    </Typography>
                    <Stack direction="row" spacing={2}>
                      <TextField
                        size="small"
                        label={"RA (°)"}
                        value={effectiveRa?.toFixed(4) ?? ""}
                        slotProps={{ input: { readOnly: true } }}
                        sx={{ flex: 1 }}
                      />
                      <TextField
                        size="small"
                        label={"Dec (°)"}
                        value={effectiveDec?.toFixed(4) ?? ""}
                        slotProps={{ input: { readOnly: true } }}
                        sx={{ flex: 1 }}
                      />
                    </Stack>
                  </Stack>
                )}
              </Box>

              {/* ── Equipment hints ── */}
              <EquipmentSection
                equipmentMode={equipmentMode}
                setEquipmentMode={setEquipmentMode}
                selectedRigId={selectedRigId}
                setSelectedRigId={setSelectedRigId}
                selectedConfigId={selectedConfigId}
                setSelectedConfigId={setSelectedConfigId}
                selectedCameraId={selectedCameraId}
                setSelectedCameraId={setSelectedCameraId}
                focalLength={focalLength}
                setFocalLength={setFocalLength}
                pixelSize={pixelSize}
                setPixelSize={setPixelSize}
                binning={binning}
                setBinning={setBinning}
                rigs={rigsQuery.data}
                equipmentOptions={equipQuery.data}
                fovInfo={fovInfo}
              />
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={
              solving
                ? () => {
                    handleCancel();
                    onClose();
                  }
                : onClose
            }
            size="small"
          >
            {result ? "Close" : "Cancel"}
          </Button>
          {canSolve && (
            <Button variant="contained" size="small" onClick={handleSolve}>
              Solve
            </Button>
          )}
          {result && !result.solved && configured && (
            <Button
              variant="contained"
              size="small"
              onClick={() => {
                setResult(null);
                setError(null);
              }}
            >
              Retry
            </Button>
          )}
        </DialogActions>
      </Dialog>

      <FileBrowser
        open={referenceBrowserOpen}
        onClose={() => setReferenceBrowserOpen(false)}
        onSelect={(path) => {
          setReferenceBrowserOpen(false);
          handleReferenceSelect(path);
        }}
        activePath={referencePath}
      />
    </>
  );
}

// ── Equipment section ───────────────────────────────────────────────

interface EquipmentSectionProps {
  equipmentMode: EquipmentMode | null;
  setEquipmentMode: (m: EquipmentMode | null) => void;
  selectedRigId: number | null;
  setSelectedRigId: (id: number | null) => void;
  selectedConfigId: number | null;
  setSelectedConfigId: (id: number | null) => void;
  selectedCameraId: number | null;
  setSelectedCameraId: (id: number | null) => void;
  focalLength: string;
  setFocalLength: (v: string) => void;
  pixelSize: string;
  setPixelSize: (v: string) => void;
  binning: number;
  setBinning: (v: number) => void;
  rigs: Rig[] | undefined;
  equipmentOptions:
    | { telescopes: { telescope_id: number; telescope_name: string; manufacturer_name: string; is_mine: boolean; configs: TelescopeConfigOption[] }[]; cameras: CameraOption[] }
    | undefined;
  fovInfo: { pixelScale: number; fovH: number | null } | null;
}

function EquipmentSection({
  equipmentMode,
  setEquipmentMode,
  selectedRigId,
  setSelectedRigId,
  selectedConfigId,
  setSelectedConfigId,
  selectedCameraId,
  setSelectedCameraId,
  focalLength,
  setFocalLength,
  pixelSize,
  setPixelSize,
  binning,
  setBinning,
  rigs,
  equipmentOptions,
  fovInfo,
}: EquipmentSectionProps) {
  const handleModeChange = (value: string) => {
    if (value === equipmentMode) {
      setEquipmentMode(null);
    } else {
      setEquipmentMode(value as EquipmentMode);
    }
  };

  // Flatten telescope configs into a single list for the dropdown
  const configOptions = useMemo(() => {
    if (!equipmentOptions) return [];
    const opts: { id: number; label: string }[] = [];
    for (const t of equipmentOptions.telescopes) {
      for (const c of t.configs) {
        opts.push({
          id: c.id,
          label: `${t.telescope_name} — ${c.config_name} (${c.effective_focal_length_mm}mm)`,
        });
      }
    }
    return opts;
  }, [equipmentOptions]);

  return (
    <Box
      sx={{
        bgcolor: "action.hover",
        borderRadius: 1,
        p: 1.5,
      }}
    >
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Equipment hints (optional)
      </Typography>

      <RadioGroup
        row
        value={equipmentMode ?? ""}
        onChange={(e) => handleModeChange(e.target.value)}
        sx={{ mb: 1, gap: 0 }}
      >
        <FormControlLabel
          value="rig"
          control={<Radio size="small" />}
          label={<Typography variant="caption">Rig</Typography>}
          sx={{ mr: 2 }}
        />
        <FormControlLabel
          value="equipment"
          control={<Radio size="small" />}
          label={<Typography variant="caption">Equipment</Typography>}
          sx={{ mr: 2 }}
        />
        <FormControlLabel
          value="manual"
          control={<Radio size="small" />}
          label={<Typography variant="caption">Manual</Typography>}
        />
      </RadioGroup>

      {equipmentMode === "rig" && (
        <Stack direction="row" spacing={1} alignItems="center">
          <FormControl size="small" sx={{ flex: 1 }}>
            <Select
              value={selectedRigId ?? ""}
              onChange={(e) => setSelectedRigId(e.target.value ? Number(e.target.value) : null)}
              displayEmpty
            >
              <MenuItem value="">
                <em>Select rig...</em>
              </MenuItem>
              {rigs?.map((r) => (
                <MenuItem key={r.id} value={r.id}>
                  {r.name} ({r.telescope_config_name}, {r.camera_name})
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <BinningSelect value={binning} onChange={setBinning} />
        </Stack>
      )}

      {equipmentMode === "equipment" && (
        <Stack spacing={1}>
          <FormControl size="small" fullWidth>
            <Select
              value={selectedConfigId ?? ""}
              onChange={(e) =>
                setSelectedConfigId(
                  e.target.value ? Number(e.target.value) : null,
                )
              }
              displayEmpty
            >
              <MenuItem value="">
                <em>OTA configuration...</em>
              </MenuItem>
              {configOptions.map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Stack direction="row" spacing={1} alignItems="center">
            <FormControl size="small" sx={{ flex: 1 }}>
              <Select
                value={selectedCameraId ?? ""}
                onChange={(e) =>
                  setSelectedCameraId(
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
                displayEmpty
              >
                <MenuItem value="">
                  <em>Camera...</em>
                </MenuItem>
                {equipmentOptions?.cameras.map((c) => (
                  <MenuItem key={c.id} value={c.id}>
                    {c.manufacturer_name} {c.model_name} ({c.pixel_size_um}
                    {"µm"})
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <BinningSelect value={binning} onChange={setBinning} />
          </Stack>
        </Stack>
      )}

      {equipmentMode === "manual" && (
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            size="small"
            label="Focal length (mm)"
            type="number"
            value={focalLength}
            onChange={(e) => setFocalLength(e.target.value)}
            sx={{ flex: 1 }}
            slotProps={{ htmlInput: { min: 1 } }}
          />
          <TextField
            size="small"
            label={`Pixel size (µm)`}
            type="number"
            value={pixelSize}
            onChange={(e) => setPixelSize(e.target.value)}
            sx={{ flex: 1 }}
            slotProps={{ htmlInput: { min: 0.1, step: 0.01 } }}
          />
          <BinningSelect value={binning} onChange={setBinning} />
        </Stack>
      )}

      {/* FOV feedback */}
      {fovInfo && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ mt: 1, display: "block" }}
        >
          Pixel scale: {fovInfo.pixelScale.toFixed(2)} arcsec/px
          {fovInfo.fovH != null && (
            <>
              {" · "}
              FOV height: {(fovInfo.fovH * 60).toFixed(1)}
              {"′"}
            </>
          )}
        </Typography>
      )}

      {equipmentMode == null && (
        <Typography variant="caption" color="text.secondary">
          No equipment selected — ASTAP will scan all scales (slower)
        </Typography>
      )}
    </Box>
  );
}

// ── Binning dropdown ────────────────────────────────────────────────

function BinningSelect({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <FormControl size="small" sx={{ minWidth: 70 }}>
      <Select value={value} onChange={(e) => onChange(Number(e.target.value))}>
        {BINNING_OPTIONS.map((b) => (
          <MenuItem key={b} value={b}>
            {b}{"×"}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

// ── Solve results ───────────────────────────────────────────────────

function SolveResults({
  result,
  onCopy,
}: {
  result: PlateSolveResult;
  onCopy: () => void;
}) {
  const rows: Array<{ label: string; value: string }> = [];

  if (result.ra_hms && result.ra_deg != null) {
    rows.push({
      label: "RA",
      value: `${result.ra_hms}  (${result.ra_deg.toFixed(4)}°)`,
    });
  }
  if (result.dec_dms && result.dec_deg != null) {
    rows.push({
      label: "Dec",
      value: `${result.dec_dms}  (${result.dec_deg.toFixed(4)}°)`,
    });
  }
  if (result.pixel_scale_arcsec != null) {
    rows.push({
      label: "Pixel scale",
      value: `${result.pixel_scale_arcsec.toFixed(3)} arcsec/px`,
    });
  }
  if (result.rotation_deg != null) {
    rows.push({
      label: "Rotation",
      value: `${result.rotation_deg.toFixed(3)}°`,
    });
  }
  if (result.fov_width_arcmin != null && result.fov_height_arcmin != null) {
    rows.push({
      label: "Field of view",
      value: `${result.fov_width_arcmin.toFixed(1)}′ × ${result.fov_height_arcmin.toFixed(1)}′`,
    });
  }
  if (result.image_width != null && result.image_height != null) {
    rows.push({
      label: "Image size",
      value: `${result.image_width} × ${result.image_height} px`,
    });
  }

  return (
    <Stack spacing={1.5}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Alert severity="info" sx={{ flex: 1, py: 0.25 }}>
          Solved
          {result.solve_time_seconds != null
            ? ` in ${result.solve_time_seconds}s`
            : ""}
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
    </Stack>
  );
}
