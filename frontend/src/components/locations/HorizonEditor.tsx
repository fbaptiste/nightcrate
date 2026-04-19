import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Slider from "@mui/material/Slider";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import { RIG_ORANGE } from "@/lib/rigColors";
import { reduceHorizon } from "@/lib/horizonReduce";

import HorizonChart, { type HorizonPoint, type AltitudeRange } from "./HorizonChart";
import HorizonEditorToolbar, { type ExportFormat } from "./HorizonEditorToolbar";
import HorizonPointEditPopover from "./HorizonPointEditPopover";

const HISTORY_CAP = 50;

interface HistoryEntry {
  points: HorizonPoint[];
  reference: HorizonPoint[] | null;
}

function clonePoints(pts: HorizonPoint[]): HorizonPoint[] {
  return pts.map((p) => ({ ...p }));
}

function sortPoints(pts: HorizonPoint[]): HorizonPoint[] {
  return [...pts].sort((a, b) => a.azimuth_deg - b.azimuth_deg);
}

function samePoints(a: HorizonPoint[], b: HorizonPoint[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i].azimuth_deg !== b[i].azimuth_deg || a[i].altitude_deg !== b[i].altitude_deg) {
      return false;
    }
  }
  return true;
}

export interface HorizonEditorProps {
  open: boolean;
  locationName: string;
  initialPoints: HorizonPoint[] | null;
  onClose: () => void;
  /**
   * Called when the user clicks "Keep changes". The contract is **stage,
   * don't persist** — the parent holds the result in memory until the
   * outer Location editor's Save persists everything together. No
   * network I/O should happen inside this callback.
   */
  onSave: (points: HorizonPoint[]) => Promise<void>;
  /**
   * Called when the user picks a file to import. The parent should
   * parse the file (via the stateless ``POST /api/horizons/parse``
   * endpoint) and return the resulting points + warnings. No DB write.
   */
  onImport: (file: File) => Promise<{ points: HorizonPoint[]; warnings: string[] }>;
  onExport: (format: ExportFormat) => void;
  /**
   * When true, the parent has staged unsaved changes — Export would
   * serve stale data, so we disable the menu with a tooltip.
   */
  exportsDisabled?: boolean;
}

export default function HorizonEditor({
  open,
  locationName,
  initialPoints,
  onClose,
  onSave,
  onImport,
  onExport,
  exportsDisabled,
}: HorizonEditorProps) {
  const seed = useMemo(
    () => (initialPoints ? sortPoints(initialPoints) : []),
    [initialPoints],
  );

  const [points, setPoints] = useState<HorizonPoint[]>(seed);
  const [savedPoints, setSavedPoints] = useState<HorizonPoint[]>(seed);
  const [history, setHistory] = useState<HistoryEntry[]>([{ points: seed, reference: null }]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [altitudeRange, setAltitudeRange] = useState<AltitudeRange>("fit");
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [confirmClearTrace, setConfirmClearTrace] = useState(false);
  const [tooFewPointsOpen, setTooFewPointsOpen] = useState(false);
  const [reduceOpen, setReduceOpen] = useState(false);
  const [reduceTolerance, setReduceTolerance] = useState(0.5);
  const [reduceOriginal, setReduceOriginal] = useState<HorizonPoint[]>([]);
  // Snapshot of the horizon at editor-open time. Used by the Compare
  // toggle to overlay the "as loaded" shape against the current edits.
  // Captured once per editor session and never mutated by slider/edit ops.
  const [sessionOriginal, setSessionOriginal] = useState<HorizonPoint[]>([]);
  const [showOriginal, setShowOriginal] = useState(false);
  // True iff the user has just hit Trace and hasn't done anything since.
  // When true, clicking × on the chip reverts the Trace in one step
  // instead of committing a separate "clear reference" entry.
  const traceUntouchedRef = useRef(false);
  const [smoothed, setSmoothed] = useState(false);
  const [referencePoints, setReferencePoints] = useState<HorizonPoint[] | null>(null);
  const [snack, setSnack] = useState<{ severity: "success" | "warning" | "error"; msg: string } | null>(
    null,
  );
  const [popoverAnchor, setPopoverAnchor] = useState<HTMLElement | null>(null);
  const [popoverPointIndex, setPopoverPointIndex] = useState<number | null>(null);

  // Container ref for sizing the chart
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const [chartWidth, setChartWidth] = useState(960);

  // Separate container for the Reduce-dialog preview chart
  const reduceChartContainerRef = useRef<HTMLDivElement | null>(null);
  const [reduceChartWidth, setReduceChartWidth] = useState(600);

  // Re-seed state when the dialog opens
  useEffect(() => {
    if (open) {
      setPoints(seed);
      setSavedPoints(seed);
      setHistory([{ points: seed, reference: null }]);
      setHistoryIndex(0);
      setAltitudeRange("fit");
      setSmoothed(false);
      setReferencePoints(null);
      setSessionOriginal(clonePoints(seed));
      // Default Compare to on when there's a horizon to compare against.
      // If the editor opened on an empty location, nothing to overlay.
      setShowOriginal(seed.length >= 2);
      traceUntouchedRef.current = false;
    }
  }, [open, seed]);

  // Preview for the Reduce dialog — recomputed as the slider moves. Pinned
  // to reduceOriginal (snapshotted on open), not live ``points``, so the
  // memo doesn't re-run during unrelated editor state churn.
  const reducedPreview = useMemo(
    () => (reduceOpen ? reduceHorizon(reduceOriginal, reduceTolerance) : reduceOriginal),
    [reduceOpen, reduceTolerance, reduceOriginal],
  );
  const reducePreviewCount = reducedPreview.length;

  // Resize observer for the chart
  useEffect(() => {
    if (!open) return;
    const el = chartContainerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setChartWidth(Math.max(480, Math.floor(w)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [open]);

  // Resize observer for the Reduce-dialog preview chart
  useEffect(() => {
    if (!reduceOpen) return;
    const el = reduceChartContainerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setReduceChartWidth(Math.max(400, Math.floor(w)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [reduceOpen]);

  const isDirty = !samePoints(points, savedPoints);
  const canUndo = historyIndex > 0;
  const canRedo = historyIndex < history.length - 1;
  // Export streams the currently-persisted server state. Parent disables
  // exports while it has staged unsaved changes (exportsDisabled).
  const canExport = !exportsDisabled && savedPoints.length >= 2;

  const commit = useCallback(
    (next: HorizonPoint[], nextReference?: HorizonPoint[] | null) => {
      // nextReference === undefined  → leave reference unchanged
      // nextReference === null       → clear reference
      // nextReference is an array    → set reference
      const refForSnapshot =
        nextReference === undefined ? referencePoints : nextReference;
      setPoints(next);
      if (nextReference !== undefined) setReferencePoints(nextReference);
      setHistory((h) => {
        const truncated = h.slice(0, historyIndex + 1);
        const appended = [...truncated, { points: next, reference: refForSnapshot }];
        const capped = appended.length > HISTORY_CAP ? appended.slice(-HISTORY_CAP) : appended;
        setHistoryIndex(capped.length - 1);
        return capped;
      });
      // Any commit other than the Trace action itself invalidates the
      // "untouched after trace" shortcut. handleUseAsReference re-sets
      // it to true after calling commit().
      traceUntouchedRef.current = false;
    },
    [historyIndex, referencePoints],
  );

  const handlePointAdd = (az: number, alt: number) => {
    const existing = points.find((p) => p.azimuth_deg === az);
    const next = existing
      ? points // don't duplicate — user can drag the existing point
      : sortPoints([...points, { azimuth_deg: az, altitude_deg: alt }]);
    if (next !== points) commit(next);
  };

  // Drag in progress — update state but don't push to history per spec.
  const handlePointDrag = (index: number, az: number, alt: number) => {
    setPoints((prev) => {
      const next = [...prev];
      next[index] = { azimuth_deg: az, altitude_deg: alt };
      return next;
    });
  };

  // Drag ended — commit the final position to history.
  const handlePointDragEnd = () => {
    commit(sortPoints(points));
  };

  const handlePointDelete = (index: number) => {
    commit(points.filter((_, i) => i !== index));
  };

  const handlePointEditStart = (index: number) => {
    // Anchor the popover at the SVG circle for that index
    const circle = document.querySelector<HTMLElement>(
      `[data-horizon-editor] svg circle:nth-of-type(${index + 1})`,
    );
    setPopoverAnchor(circle ?? chartContainerRef.current);
    setPopoverPointIndex(index);
  };

  const handlePointEditCommit = (index: number, az: number, alt: number) => {
    const next = [...points];
    next[index] = { azimuth_deg: az, altitude_deg: alt };
    commit(sortPoints(next));
  };

  const restoreFromHistory = (entry: HistoryEntry) => {
    setPoints(clonePoints(entry.points));
    setReferencePoints(entry.reference ? clonePoints(entry.reference) : null);
  };

  const handleUndo = useCallback(() => {
    if (historyIndex > 0) {
      const nextIdx = historyIndex - 1;
      setHistoryIndex(nextIdx);
      restoreFromHistory(history[nextIdx]);
      traceUntouchedRef.current = false;
    }
  }, [history, historyIndex]);

  const handleRedo = useCallback(() => {
    if (historyIndex < history.length - 1) {
      const nextIdx = historyIndex + 1;
      setHistoryIndex(nextIdx);
      restoreFromHistory(history[nextIdx]);
      traceUntouchedRef.current = false;
    }
  }, [history, historyIndex]);

  const handleReset = () => setConfirmReset(true);
  const confirmResetAction = () => {
    setConfirmReset(false);
    commit([]);
  };

  const handleReduceApply = () => {
    setReduceOpen(false);
    if (reducedPreview.length !== reduceOriginal.length) commit(reducedPreview);
  };

  const handleUseAsReference = () => {
    if (points.length < 2) return;
    // Single atomic commit: move current points to the faded guide and
    // clear the editable line. Undo reverses both in one step.
    commit([], clonePoints(points));
    // commit() clears the flag; re-arm it after — we're now in the
    // "traced, not yet edited" state.
    traceUntouchedRef.current = true;
  };

  const handleClearReference = () => {
    if (traceUntouchedRef.current) {
      // User hit Trace but hasn't done anything since. The × is a
      // "cancel the trace" action — revert in one undo step instead
      // of committing a separate clear.
      handleUndo();
      return;
    }
    if (referencePoints) {
      // The user has edited points since tracing — ask whether those
      // new edits should stick around or be thrown out for the traced
      // original shape.
      setConfirmClearTrace(true);
      return;
    }
    commit(points, null);
  };

  const confirmClearTraceDiscard = () => {
    setConfirmClearTrace(false);
    if (!referencePoints) return;
    // Throw away new edits; restore the traced points as the editable
    // line and clear the reference. Committed, so undoable.
    commit(clonePoints(referencePoints), null);
  };

  const confirmClearTraceKeep = () => {
    setConfirmClearTrace(false);
    // Keep the user's new points; just remove the ghost overlay.
    commit(points, null);
  };

  const handleImport = async (file: File) => {
    try {
      const { points: imported, warnings } = await onImport(file);
      if (imported.length < 2) {
        setSnack({ severity: "error", msg: "Import produced fewer than 2 points." });
        return;
      }
      commit(sortPoints(imported));
      setSnack({
        severity: warnings.length > 0 ? "warning" : "success",
        msg:
          warnings.length > 0
            ? `Imported with ${warnings.length} warning${warnings.length === 1 ? "" : "s"}.`
            : `Imported ${imported.length} points.`,
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Import failed.";
      setSnack({ severity: "error", msg });
    }
  };

  const handleSave = async () => {
    if (points.length < 2) {
      setTooFewPointsOpen(true);
      return;
    }
    try {
      // "Keep changes" stages the points in the parent. No DB write here.
      // The parent (Location editor) persists on its own Save.
      await onSave(points);
      setSavedPoints(clonePoints(points));
      onClose();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to keep changes.";
      setSnack({ severity: "error", msg });
    }
  };

  const handleClose = () => {
    if (isDirty) {
      setConfirmDiscard(true);
    } else {
      onClose();
    }
  };

  // Keyboard shortcuts: Cmd/Ctrl-Z, Cmd/Ctrl-Shift-Z
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;
      if (e.key === "z" || e.key === "Z") {
        e.preventDefault();
        if (e.shiftKey) handleRedo();
        else handleUndo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, handleUndo, handleRedo]);

  return (
    <>
      <Dialog open={open} onClose={handleClose} maxWidth="lg" fullWidth>
        <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1, pr: 1 }}>
          <Box sx={{ flex: 1 }}>
            Horizon Editor &mdash; {locationName}
            {isDirty && (
              <Typography component="span" variant="caption" color="warning.main" sx={{ ml: 1 }}>
                (unsaved)
              </Typography>
            )}
          </Box>
          <IconButton aria-label="close" onClick={handleClose} size="small">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent data-horizon-editor dividers>
          <Stack spacing={2}>
            <HorizonEditorToolbar
              pointCount={points.length}
              altitudeRange={altitudeRange}
              canUndo={canUndo}
              canRedo={canRedo}
              canExport={canExport}
              canReduce={points.length >= 3}
              smoothed={smoothed}
              referenceCount={referencePoints?.length ?? 0}
              canShowOriginal={sessionOriginal.length >= 2}
              showOriginal={showOriginal}
              onAltitudeRangeChange={setAltitudeRange}
              onUndo={handleUndo}
              onRedo={handleRedo}
              onReset={handleReset}
              onReduce={() => {
                setReduceOriginal(clonePoints(points));
                setReduceTolerance(0.5);
                setReduceOpen(true);
              }}
              onSmoothedChange={setSmoothed}
              onShowOriginalChange={setShowOriginal}
              onImport={handleImport}
              onExport={onExport}
              onUseAsReference={handleUseAsReference}
              onClearReference={handleClearReference}
            />
            <Box ref={chartContainerRef} sx={{ width: "100%", minHeight: 420 }}>
              <HorizonChart
                points={points}
                referencePoints={referencePoints}
                originalPoints={showOriginal ? sessionOriginal : null}
                mode={smoothed ? "readonly" : "editable"}
                altitudeRange={altitudeRange}
                showRawPoints={false}
                width={chartWidth}
                height={420}
                onPointAdd={handlePointAdd}
                onPointDrag={handlePointDrag}
                onPointDragEnd={handlePointDragEnd}
                onPointEditStart={handlePointEditStart}
              />
            </Box>
            {smoothed ? (
              <Typography variant="caption" color="text.secondary">
                Smooth preview — editing disabled. Turn Smooth off to continue editing.
              </Typography>
            ) : (
              <Stack spacing={0.4} sx={{ color: "text.secondary" }}>
                <Typography variant="caption">
                  <strong>Editing</strong> &mdash; double-click empty area to add a point;
                  drag a point to move it; right-click a point to enter precise values or
                  delete it. &#8984;Z / &#8984;&#8679;Z to undo / redo.
                </Typography>
                <Typography variant="caption">
                  <strong>Reduce</strong> &mdash; simplifies a dense horizon (e.g. a 60-point
                  Theodolite import) into fewer representative points while preserving the
                  altitude shape within a tolerance you choose.
                </Typography>
                <Typography variant="caption">
                  <strong>Trace from current</strong> &mdash; freezes your current points as
                  a faded guide and clears the editable line so you can redraw a cleaner
                  version over the same shape. The guide is discarded on save; Undo or the
                  chip&rsquo;s &times; brings it back.
                </Typography>
                <Typography variant="caption">
                  <strong>Compare</strong> &mdash; overlays the horizon as it was when
                  you opened the editor (dotted blue) so you can see how far your edits
                  have moved from the starting shape.
                </Typography>
                <Typography variant="caption">
                  <strong>Smooth</strong> &mdash; shows a spline-smoothed preview of your
                  horizon. Editing is disabled while on. Does not change the saved data.
                </Typography>
                <Typography variant="caption">
                  A horizon needs at least 2 points to save.
                </Typography>
              </Stack>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Discard changes</Button>
          <Button variant="contained" onClick={handleSave} disabled={!isDirty}>
            Keep changes
          </Button>
        </DialogActions>
      </Dialog>

      <HorizonPointEditPopover
        anchorEl={popoverAnchor}
        point={popoverPointIndex !== null ? points[popoverPointIndex] : null}
        pointIndex={popoverPointIndex}
        onCommit={handlePointEditCommit}
        onDelete={handlePointDelete}
        onClose={() => {
          setPopoverAnchor(null);
          setPopoverPointIndex(null);
        }}
      />

      {/* Confirm discard dialog */}
      <Dialog open={confirmDiscard} onClose={() => setConfirmDiscard(false)}>
        <DialogTitle>Discard unsaved changes?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            You have unsaved changes to the horizon for {locationName}. Close anyway?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDiscard(false)}>Keep editing</Button>
          <Button
            color="warning"
            onClick={() => {
              setConfirmDiscard(false);
              onClose();
            }}
          >
            Discard
          </Button>
        </DialogActions>
      </Dialog>

      {/* Reduce dialog */}
      <Dialog open={reduceOpen} onClose={() => setReduceOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Reduce horizon points</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            Simplifies your horizon using Douglas&ndash;Peucker, keeping the
            altitude shape accurate to within the tolerance below. Useful for
            trimming dense imports (e.g. Theodolite) to a handful of
            representative points.
          </DialogContentText>
          <Typography variant="body2" sx={{ mb: 0.5 }}>
            Altitude tolerance: {reduceTolerance.toFixed(1)}&deg;
          </Typography>
          <Slider
            value={reduceTolerance}
            min={0.1}
            max={5}
            step={0.1}
            onChange={(_, v) => setReduceTolerance(Array.isArray(v) ? v[0] : v)}
            valueLabelDisplay="auto"
          />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1, mb: 2 }}>
            {reduceOriginal.length} &rarr; <strong>{reducePreviewCount}</strong> points
          </Typography>

          <Box ref={reduceChartContainerRef} sx={{ width: "100%" }}>
            <HorizonChart
              points={reducedPreview}
              referencePoints={reduceOriginal}
              mode="readonly"
              altitudeRange="fit"
              width={reduceChartWidth}
              height={220}
            />
          </Box>

          <Stack direction="row" spacing={3} sx={{ mt: 1.5, pl: 1 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Box
                sx={{
                  width: 22,
                  height: 0,
                  borderTop: `2px dashed ${RIG_ORANGE}`,
                  opacity: 0.6,
                }}
              />
              <Typography variant="caption" color="text.secondary">
                Original ({reduceOriginal.length} pts)
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1} alignItems="center">
              <Box
                sx={{
                  width: 22,
                  height: 0,
                  borderTop: `2px solid ${RIG_ORANGE}`,
                }}
              />
              <Typography variant="caption" color="text.secondary">
                Reduced ({reducePreviewCount} pts)
              </Typography>
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReduceOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleReduceApply}
            disabled={reducePreviewCount === reduceOriginal.length}
          >
            Apply
          </Button>
        </DialogActions>
      </Dialog>

      {/* Too-few-points dialog */}
      <Dialog open={tooFewPointsOpen} onClose={() => setTooFewPointsOpen(false)}>
        <DialogTitle>Add more points</DialogTitle>
        <DialogContent>
          <DialogContentText>
            A horizon needs at least 2 points to interpolate a 360&deg; profile.
            Double-click anywhere on the chart to add more points, then try saving again.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button variant="contained" onClick={() => setTooFewPointsOpen(false)}>
            OK
          </Button>
        </DialogActions>
      </Dialog>

      {/* Clear-trace dialog — shown when × is clicked on the Tracing chip
          and the user has edited points since tracing. */}
      <Dialog open={confirmClearTrace} onClose={() => setConfirmClearTrace(false)}>
        <DialogTitle>Clear tracing reference?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            You&rsquo;ve edited points since starting the trace. Do you want to keep
            your new points, or discard them and restore the traced original?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmClearTrace(false)}>Cancel</Button>
          <Button color="warning" onClick={confirmClearTraceDiscard}>
            Discard new points
          </Button>
          <Button variant="contained" onClick={confirmClearTraceKeep}>
            Keep new points
          </Button>
        </DialogActions>
      </Dialog>

      {/* Confirm clear dialog */}
      <Dialog open={confirmReset} onClose={() => setConfirmReset(false)}>
        <DialogTitle>Clear all points?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This removes every point from your horizon, returning to the empty
            starting state. You can still undo after clearing.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmReset(false)}>Cancel</Button>
          <Button color="warning" onClick={confirmResetAction}>
            Clear
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snack !== null}
        autoHideDuration={snack?.severity === "success" ? 2000 : 4000}
        onClose={() => setSnack(null)}
        message={snack?.msg}
      />
    </>
  );
}
