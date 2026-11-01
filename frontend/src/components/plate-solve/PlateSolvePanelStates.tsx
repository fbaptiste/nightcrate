import type { Dispatch, SetStateAction } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { alpha, useTheme } from "@mui/material/styles";

import type { DsoListItem } from "@/api/dsos";
import type { PlateSolver, ProgressSnapshot } from "@/api/plateSolve";
import type { Rig } from "@/api/rigs";
import {
  type AppliedHints,
  type HeaderHints,
  type PositionHint,
  type ScaleHint,
} from "./hintModel";
import {
  buttonSx,
  formatHintNumber,
  formatPosition,
  noteSx,
  panelSx,
  scaleValue,
} from "./panelHelpers";
import SolveSteps from "./SolveSteps";
import type { FailureState } from "./useSolveOperation";

const fieldsSx = {
  gridColumn: 2,
  display: "flex",
  flexWrap: "wrap",
  gap: 1,
  mt: 0.5,
  "& > *": { flex: "1 1 90px", minWidth: 0 },
} as const;

function SummaryRow({
  label,
  value,
  sub,
  aria,
  onChange,
}: {
  label: string;
  value: string;
  sub: string;
  aria: string;
  onChange: () => void;
}) {
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "1fr auto",
        gap: "2px 10px",
        py: 1.25,
        borderBottom: 1,
        borderColor: "divider",
      }}
    >
      <Typography
        color="text.secondary"
        sx={{ gridColumn: "1 / -1", fontSize: 12 }}
      >
        {label}
      </Typography>
      <Box sx={{ minWidth: 0 }}>
        <Typography sx={{ fontSize: 14 }}>{value}</Typography>
        <Typography
          color="text.secondary"
          sx={{ fontSize: 12.5, fontVariantNumeric: "tabular-nums" }}
        >
          {sub}
        </Typography>
      </Box>
      <Button
        variant="text"
        aria-label={aria}
        onClick={onChange}
        sx={{ minHeight: 32, px: 0.5, alignSelf: "start" }}
      >
        Change
      </Button>
    </Box>
  );
}

interface SummaryProps {
  applied: AppliedHints;
  positionSummary: string[];
  scaleSummary: string[];
  primaryLabel: string;
  replacing: boolean;
  solverAvailable: boolean;
  astapAvailable: boolean;
  onEdit: () => void;
  onSolve: () => void;
  onSetup: () => void;
  onOpenSettings: () => void;
  onUseAstap: () => void;
  dismiss?: { label: string; onClick: () => void };
}

export function PanelSummary({
  applied,
  positionSummary,
  scaleSummary,
  primaryLabel,
  replacing,
  solverAvailable,
  astapAvailable,
  onEdit,
  onSolve,
  onSetup,
  onOpenSettings,
  onUseAstap,
  dismiss,
}: SummaryProps) {
  const theme = useTheme();
  return (
    <Box sx={panelSx} aria-label="Plate solve">
      <Typography component="h2" sx={{ fontSize: 15, fontWeight: 600 }}>
        Plate solve
      </Typography>
      {replacing && (
        <Box
          sx={{
            borderRadius: "6px",
            p: "10px 12px",
            bgcolor: alpha(theme.palette.primary.main, 0.1),
            border: `1px solid ${alpha(theme.palette.primary.main, 0.4)}`,
          }}
        >
          <Typography sx={{ fontWeight: 600, fontSize: 13 }}>Not saved yet</Typography>
          <Typography color="text.secondary" sx={{ fontSize: 13 }}>
            Your saved solution stays until this solve succeeds.
          </Typography>
        </Box>
      )}
      <Box sx={{ borderTop: 1, borderColor: "divider" }}>
        <SummaryRow
          label="Starting position"
          value={positionSummary[0]}
          sub={positionSummary[1]}
          aria="Change starting position"
          onChange={onEdit}
        />
        <SummaryRow
          label="Pixel scale"
          value={scaleSummary[0]}
          sub={scaleSummary[1]}
          aria="Change pixel scale"
          onChange={onEdit}
        />
        <SummaryRow
          label="Solver"
          value={applied.solver === "native" ? "Built-in" : "ASTAP"}
          sub={
            applied.solver === "native" ? "Gaia DR3 star data" : "Your ASTAP installation"
          }
          aria="Change solver"
          onChange={onEdit}
        />
      </Box>
      <Typography color="text.secondary" sx={{ fontSize: 12.5 }}>
        These guide the first search. If it finds nothing, the solver widens the search by
        itself.
      </Typography>
      {!solverAvailable && applied.solver === "native" && (
        <Box sx={noteSx(theme.palette.secondary.main)}>
          <Typography sx={{ fontSize: 13 }}>
            The built-in solver needs its star data, a one-time 1.14 GB download.
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
            <Button variant="outlined" onClick={onSetup} sx={buttonSx}>
              Set up plate-solving stars
            </Button>
            {astapAvailable && (
              <Button variant="text" onClick={onUseAstap} sx={buttonSx}>
                Use ASTAP instead
              </Button>
            )}
          </Box>
        </Box>
      )}
      {!solverAvailable && applied.solver === "astap" && (
        <Box sx={noteSx(theme.palette.secondary.main)}>
          <Typography sx={{ fontSize: 13 }}>
            ASTAP executable path is not configured. Set it in Settings before plate solving.
          </Typography>
          <Button variant="text" onClick={onOpenSettings} sx={{ ...buttonSx, alignSelf: "flex-start" }}>
            Open Settings
          </Button>
        </Box>
      )}
      <Button
        variant="contained"
        disabled={!solverAvailable}
        onClick={onSolve}
        sx={{ ...buttonSx, width: "100%" }}
      >
        {primaryLabel}
      </Button>
      {dismiss && (
        <Button
          variant="text"
          color="inherit"
          onClick={dismiss.onClick}
          sx={{ ...buttonSx, width: "100%", color: "text.secondary" }}
        >
          {dismiss.label}
        </Button>
      )}
    </Box>
  );
}

export function PanelSolving({
  solver,
  progress,
  onCancel,
}: {
  solver: PlateSolver | null;
  progress: ProgressSnapshot | null;
  onCancel: () => void;
}) {
  return (
    <Box sx={panelSx} aria-live="polite">
      <Typography component="h2" sx={{ fontSize: 15, fontWeight: 600 }}>
        Solving with {solver === "astap" ? "ASTAP" : "Built-in"}{" "}
        <Box
          component="span"
          color="text.secondary"
          sx={{ fontVariantNumeric: "tabular-nums", fontSize: 12.5 }}
        >
          · {Math.floor(progress?.elapsed_seconds ?? 0)} s
        </Box>
      </Typography>
      <SolveSteps snapshot={progress} />
      {solver === "astap" && (
        <Typography color="text.secondary" sx={{ fontSize: 12.5 }}>
          A search without a position can take up to 3 minutes. You can cancel at any time.
        </Typography>
      )}
      <Button variant="outlined" onClick={onCancel} sx={buttonSx}>
        Cancel solve
      </Button>
    </Box>
  );
}

interface FailureProps {
  failure: FailureState;
  progress: ProgressSnapshot | null;
  missColor: string;
  nativeAvailable: boolean;
  astapAvailable: boolean;
  onChangeHints: () => void;
  onOtherSolver: (solver: PlateSolver) => void;
  onRetry: () => void;
  onChooseImage: () => void;
}

export function PanelFailure({
  failure,
  progress,
  missColor,
  nativeAvailable,
  astapAvailable,
  onChangeHints,
  onOtherSolver,
  onRetry,
  onChooseImage,
}: FailureProps) {
  const theme = useTheme();
  const other: PlateSolver = failure.solver === "native" ? "astap" : "native";
  const otherAvailable = other === "native" ? nativeAvailable : astapAvailable;
  const retryReasons = new Set(["cancelled", "time_limit", "error", "read_error"]);
  const preciseTitles: Record<string, string> = {
    cancelled: "Solve cancelled",
    time_limit: "Time limit reached",
    ambiguous: "Ambiguous solution",
    too_few_stars: "Too few stars",
    error: "Plate solve error",
    read_error: "Couldn't read the image",
    invalid_configuration: "Setup needed",
  };
  const canRetry =
    (failure.failureReason !== null && retryReasons.has(failure.failureReason)) ||
    (failure.failureReason === "stars_not_installed" && nativeAvailable) ||
    (failure.failureReason === "no_ranges" && nativeAvailable);

  return (
    <Box sx={panelSx}>
      <Box sx={noteSx(missColor)}>
        <Typography sx={{ fontWeight: 600 }}>
          {preciseTitles[failure.failureReason ?? ""] ?? "No solution found"}
        </Typography>
        {failure.message !== "Plate solve failed." && (
          <Typography sx={{ fontSize: 13 }}>{failure.message}</Typography>
        )}
        <Typography sx={{ fontSize: 13 }}>Your image and hints are still selected.</Typography>
      </Box>
      <Typography color="text.secondary" sx={{ fontSize: 12.5 }}>
        What {failure.solver === "astap" ? "ASTAP" : "Built-in"} tried
      </Typography>
      <SolveSteps snapshot={progress} attempts={failure.attempts} />
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
        <Button variant="contained" onClick={onChangeHints} sx={buttonSx}>
          Change hints
        </Button>
        {otherAvailable && (
          <Button variant="outlined" onClick={() => onOtherSolver(other)} sx={buttonSx}>
            Solve with {other === "astap" ? "ASTAP" : "Built-in"}
          </Button>
        )}
        {canRetry && (
          <Button variant="text" onClick={onRetry} sx={buttonSx}>
            Try again
          </Button>
        )}
      </Box>
      <Box sx={noteSx(theme.palette.secondary.main)}>
        <Typography sx={{ fontSize: 13 }}>
          Heavily processed or cropped images can have too few usable stars. The stacked image
          from before processing usually solves.
        </Typography>
        <Button
          variant="text"
          onClick={onChooseImage}
          sx={{ ...buttonSx, justifySelf: "start", px: 0.5 }}
        >
          Choose another image
        </Button>
      </Box>
    </Box>
  );
}

interface EditorProps {
  draft: AppliedHints;
  setDraft: Dispatch<SetStateAction<AppliedHints>>;
  header: HeaderHints;
  rigs: Rig[];
  targets: DsoListItem[];
  targetInput: string;
  searching: boolean;
  nativeAvailable: boolean;
  astapAvailable: boolean;
  onTargetInput: (value: string) => void;
  onPositionKind: (kind: PositionHint["kind"]) => void;
  onScaleKind: (kind: ScaleHint["kind"]) => void;
  onApply: () => void;
  onCancel: () => void;
  onReset: () => void;
}

export function PanelEditor({
  draft,
  setDraft,
  header,
  rigs,
  targets,
  targetInput,
  searching,
  nativeAvailable,
  astapAvailable,
  onTargetInput,
  onPositionKind,
  onScaleKind,
  onApply,
  onCancel,
  onReset,
}: EditorProps) {
  const selectedRigId = draft.scale.kind === "rig" ? draft.scale.rigId : null;
  const selectedRig = rigs.find((rig) => rig.id === selectedRigId);
  const validTarget = draft.position.kind !== "target" || draft.position.id > 0;
  const draftScale = scaleValue(draft.scale, header);
  const validScale =
    draft.scale.kind === "header" ||
    draft.scale.kind === "none" ||
    (draftScale ?? 0) > 0;

  const handleTargetChange = (_event: unknown, item: DsoListItem | null) => {
    if (item?.ra_deg == null || item.dec_deg == null) return;
    const label = item.common_name
      ? `${item.primary_designation}, ${item.common_name}`
      : item.primary_designation;
    setDraft((current) => ({
      ...current,
      position: {
        kind: "target",
        id: item.id,
        label,
        ra: item.ra_deg!,
        dec: item.dec_deg!,
      },
    }));
  };

  const handleRigChange = (rigId: number) => {
    const rig = rigs.find((item) => item.id === rigId);
    if (!rig) return;
    setDraft((current) => ({
      ...current,
      scale: {
        kind: "rig",
        rigId: rig.id,
        rigName: rig.name,
        focalLengthMm: rig.effective_focal_length_mm,
        pixelSizeUm: rig.pixel_size_um,
        binning: current.scale.kind === "rig" ? current.scale.binning : 1,
      },
    }));
  };

  return (
    <Box sx={panelSx} aria-label="Change hints">
      <Typography component="h2" sx={{ fontSize: 15, fontWeight: 600 }}>
        Change hints
      </Typography>
      <Box component="fieldset" sx={{ border: 0, m: 0, p: 0 }}>
        <Typography component="legend" sx={{ fontWeight: 600, fontSize: 13, mb: 0.5 }}>
          Starting position
        </Typography>
        <RadioGroup
          value={draft.position.kind}
          onChange={(event) => onPositionKind(event.target.value as PositionHint["kind"])}
        >
          <FormControlLabel
            value="header"
            control={<Radio size="small" />}
            label={
              <Box>
                Use the image header
                <Typography color="text.secondary" sx={{ fontSize: 12.5 }}>
                  {formatPosition(header.ra, header.dec)}
                </Typography>
              </Box>
            }
          />
          <FormControlLabel
            value="target"
            control={<Radio size="small" />}
            label="Choose a target"
          />
          {draft.position.kind === "target" && (
            <Box sx={fieldsSx}>
              <Autocomplete
                options={targets}
                loading={searching}
                inputValue={targetInput}
                filterOptions={(values) => values}
                getOptionLabel={(item) =>
                  item.common_name
                    ? `${item.primary_designation}, ${item.common_name}`
                    : item.primary_designation
                }
                onInputChange={(_, value, reason) => {
                  if (reason !== "reset") onTargetInput(value);
                }}
                onChange={handleTargetChange}
                renderInput={(params) => (
                  <TextField {...params} size="small" label="Target" />
                )}
              />
            </Box>
          )}
          <FormControlLabel
            value="none"
            control={<Radio size="small" />}
            label={
              <Box>
                Search without a position
                <Typography color="text.secondary" sx={{ fontSize: 12.5 }}>
                  The whole sky is searched
                </Typography>
              </Box>
            }
          />
        </RadioGroup>
      </Box>
      <Box sx={{ height: "1px", bgcolor: "divider" }} />
      <Box component="fieldset" sx={{ border: 0, m: 0, p: 0 }}>
        <Typography component="legend" sx={{ fontWeight: 600, fontSize: 13, mb: 0.5 }}>
          Pixel scale
        </Typography>
        <RadioGroup
          value={draft.scale.kind}
          onChange={(event) => onScaleKind(event.target.value as ScaleHint["kind"])}
        >
          <FormControlLabel
            value="header"
            control={<Radio size="small" />}
            label={
              <Box>
                Use the image header
                <Typography color="text.secondary" sx={{ fontSize: 12.5 }}>
                  {header.scaleArcsec != null
                    ? `${formatHintNumber(header.scaleArcsec, "scale")}″/px ` +
                      `(${header.focalLengthMm != null ? formatHintNumber(header.focalLengthMm, "focalLength") : "?"} mm, ` +
                      `${header.effectivePixelUm != null ? formatHintNumber(header.effectivePixelUm, "pixelSize") : "?"} µm)`
                    : "No scale found"}
                </Typography>
              </Box>
            }
          />
          <FormControlLabel
            value="rig"
            control={<Radio size="small" />}
            label="Use a rig"
          />
          {draft.scale.kind === "rig" && (
            <Box sx={fieldsSx}>
              <TextField
                select
                size="small"
                label="Rig"
                value={draft.scale.rigId || ""}
                onChange={(event) => handleRigChange(Number(event.target.value))}
              >
                {rigs.map((rig) => (
                  <MenuItem key={rig.id} value={rig.id}>
                    {rig.name}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                size="small"
                label="Binning"
                value={draft.scale.binning}
                onChange={(event) =>
                  setDraft((current) =>
                    current.scale.kind === "rig"
                      ? {
                          ...current,
                          scale: { ...current.scale, binning: Number(event.target.value) },
                        }
                      : current,
                  )
                }
              >
                {[1, 2, 3, 4].map((value) => (
                  <MenuItem key={value} value={value}>
                    {value}×
                  </MenuItem>
                ))}
              </TextField>
              {selectedRig && (
                <Typography
                  color="text.secondary"
                  sx={{ flexBasis: "100% !important", fontSize: 12.5 }}
                >
                  = {draftScale != null ? formatHintNumber(draftScale, "scale") : "—"}″/px
                </Typography>
              )}
            </Box>
          )}
          <FormControlLabel
            value="enter"
            control={<Radio size="small" />}
            label="Enter the pixel scale"
          />
          {draft.scale.kind === "enter" && (
            <Box sx={fieldsSx}>
              <TextField
                size="small"
                label="Pixel scale (″/px)"
                type="number"
                value={draft.scale.scaleArcsec || ""}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    scale: { kind: "enter", scaleArcsec: Number(event.target.value) },
                  }))
                }
              />
            </Box>
          )}
          <FormControlLabel
            value="calc"
            control={<Radio size="small" />}
            label="Calculate from focal length and pixel size"
          />
          {draft.scale.kind === "calc" && (
            <Box sx={fieldsSx}>
              <TextField
                size="small"
                label="Focal length (mm)"
                type="number"
                value={draft.scale.focalLengthMm || ""}
                onChange={(event) =>
                  setDraft((current) =>
                    current.scale.kind === "calc"
                      ? {
                          ...current,
                          scale: {
                            ...current.scale,
                            focalLengthMm: Number(event.target.value),
                          },
                        }
                      : current,
                  )
                }
              />
              <TextField
                size="small"
                label="Pixel size (µm)"
                type="number"
                value={draft.scale.pixelSizeUm || ""}
                onChange={(event) =>
                  setDraft((current) =>
                    current.scale.kind === "calc"
                      ? {
                          ...current,
                          scale: {
                            ...current.scale,
                            pixelSizeUm: Number(event.target.value),
                          },
                        }
                      : current,
                  )
                }
              />
              <TextField
                select
                size="small"
                label="Binning"
                value={draft.scale.binning}
                onChange={(event) =>
                  setDraft((current) =>
                    current.scale.kind === "calc"
                      ? {
                          ...current,
                          scale: { ...current.scale, binning: Number(event.target.value) },
                        }
                      : current,
                  )
                }
              >
                {[1, 2, 3, 4].map((value) => (
                  <MenuItem key={value} value={value}>
                    {value}×
                  </MenuItem>
                ))}
              </TextField>
              <Typography
                color="text.secondary"
                sx={{ flexBasis: "100% !important", fontSize: 12.5 }}
              >
                = {draftScale != null
                  ? formatHintNumber(draftScale, "scale")
                  : "—"}″/px
              </Typography>
            </Box>
          )}
          <FormControlLabel
            value="none"
            control={<Radio size="small" />}
            label={
              <Box>
                Search without a scale
                <Typography color="text.secondary" sx={{ fontSize: 12.5 }}>
                  Slower; every scale is tried
                </Typography>
              </Box>
            }
          />
        </RadioGroup>
        <Typography color="text.secondary" sx={{ fontSize: 12.5, mt: 0.5 }}>
          The scale must match this image, including any resizing or drizzle.
        </Typography>
      </Box>
      <Box sx={{ height: "1px", bgcolor: "divider" }} />
      <Box component="fieldset" sx={{ border: 0, m: 0, p: 0 }}>
        <Typography component="legend" sx={{ fontWeight: 600, fontSize: 13, mb: 0.5 }}>
          Solver
        </Typography>
        <RadioGroup
          value={draft.solver}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              solver: event.target.value as PlateSolver,
            }))
          }
        >
          <FormControlLabel
            value="native"
            control={<Radio size="small" />}
            label={
              <Box>
                Built-in
                <Typography
                  color={nativeAvailable ? "text.secondary" : "text.disabled"}
                  sx={{ fontSize: 12.5 }}
                >
                  Gaia DR3 star data. Usually under a few seconds.
                  {nativeAvailable ? "" : " Setup needed."}
                </Typography>
              </Box>
            }
          />
          <FormControlLabel
            value="astap"
            control={<Radio size="small" />}
            label={
              <Box>
                ASTAP
                <Typography
                  color={astapAvailable ? "text.secondary" : "text.disabled"}
                  sx={{ fontSize: 12.5 }}
                >
                  Your ASTAP installation. A search without a position can take up to 3 minutes.
                  {astapAvailable ? "" : " Not configured."}
                </Typography>
              </Box>
            }
          />
        </RadioGroup>
        <Typography color="text.secondary" sx={{ fontSize: 12.5 }}>
          This changes the solver for this image only. The default is in Settings.
        </Typography>
      </Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
        <Button
          variant="contained"
          disabled={!validTarget || !validScale}
          onClick={onApply}
          sx={buttonSx}
        >
          Apply
        </Button>
        <Button variant="text" onClick={onCancel} sx={buttonSx}>
          Cancel
        </Button>
        <Box sx={{ flex: 1 }} />
        <Button variant="text" onClick={onReset} sx={buttonSx}>
          Reset to image header
        </Button>
      </Box>
    </Box>
  );
}
