/**
 * Dialog for creating or editing a target plan assignment.
 *
 * Collects location + horizon + rig (required) and optional date
 * ranges + notes. Shows the Best Time of Year chart with:
 *   - Moon separation control
 *   - Shift-click-drag to add date ranges on the chart
 *   - Highlighted range zones with close buttons
 *   - Draggable hours threshold line with intersection snapping
 *   - Date picker pairs with + button for manual entry
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import { useTheme } from "@mui/material/styles";
import { fetchLocations, type Location } from "@/api/locations";
import { fetchHorizons, type Horizon } from "@/api/horizons";
import { fetchRigs, type Rig } from "@/api/rigs";
import {
  fetchAnnualHours,
  type AnnualHoursResponse,
  type AnnualHoursPoint,
} from "@/api/planner";
import { useSettingsStore } from "@/stores/settingsStore";
import {
  useCreatePlan,
  useUpdatePlan,
  type PlanSummary,
  type CreatePlanParams,
  type DateRangeIn,
} from "@/api/wishlist";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";

interface Props {
  open: boolean;
  dsoId: number;
  dsoName: string;
  existingPlan: PlanSummary | null;
  onClose: () => void;
}

const CHART_HEIGHT = 220;
const CHART_MARGIN = { top: 20, right: 56, bottom: 28, left: 40 };
const HANDLE_SIZE = 32;

export default function PlanAssignmentEditor({ open, dsoId, dsoName, existingPlan, onClose }: Props) {
  const settings = useSettingsStore((s) => s.settings);
  const [locationId, setLocationId] = useState<number | "">("");
  const [horizonId, setHorizonId] = useState<number | "">("");
  const [rigId, setRigId] = useState<number | "">("");
  const [dateRanges, setDateRanges] = useState<DateRangeIn[]>([]);
  const [notes, setNotes] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const moonSepDefault = settings?.planner_moon_sep_deg ?? 0;
  const [moonSepDeg, setMoonSepDeg] = useState<number>(moonSepDefault);
  const [moonFilterEnabled, setMoonFilterEnabled] = useState(false);
  const [maxIllumination, setMaxIllumination] = useState<number>(50);
  const [minSeparation, setMinSeparation] = useState<number>(60);
  const [moonCombine, setMoonCombine] = useState<"and" | "or">("and");

  const locationsQuery = useQuery({
    queryKey: ["locations"],
    queryFn: fetchLocations,
    staleTime: 5 * 60_000,
  });

  const horizonsQuery = useQuery({
    queryKey: ["horizons", locationId],
    queryFn: () => fetchHorizons(locationId as number),
    enabled: locationId !== "",
    staleTime: 5 * 60_000,
  });

  const rigsQuery = useQuery({
    queryKey: ["rigs"],
    queryFn: () => fetchRigs(true),
    staleTime: 5 * 60_000,
  });

  const annualHoursQuery = useQuery({
    queryKey: [
      "annual-hours", dsoId, locationId, horizonId, moonSepDeg,
      moonFilterEnabled, maxIllumination, minSeparation, moonCombine,
    ],
    queryFn: () =>
      fetchAnnualHours(dsoId, locationId as number, {
        horizonId: horizonId as number,
        moonSepDeg,
        maxIlluminationPct: moonFilterEnabled ? maxIllumination : undefined,
        minSeparationDeg: moonFilterEnabled ? minSeparation : undefined,
        moonCombine: moonFilterEnabled ? moonCombine : undefined,
      }),
    enabled: locationId !== "" && horizonId !== "" && open,
    staleTime: 60 * 60_000,
  });

  const createPlan = useCreatePlan();
  const updatePlan = useUpdatePlan();

  useEffect(() => {
    if (!open) return;
    if (existingPlan) {
      setLocationId(existingPlan.location_id);
      setHorizonId(existingPlan.horizon_id);
      setRigId(existingPlan.rig_id);
      setMoonSepDeg(existingPlan.moon_sep_deg);
      setDateRanges(
        existingPlan.date_ranges.map((r) => ({
          start_date: r.start_date,
          end_date: r.end_date,
        })),
      );
      setNotes(existingPlan.notes ?? "");
    } else {
      const defLoc = locationsQuery.data?.find((l) => l.is_default);
      setLocationId(defLoc ? defLoc.id : "");
      setHorizonId("");
      const defRig = rigsQuery.data?.find((r) => r.is_default);
      setRigId(defRig ? defRig.id : "");
      setMoonSepDeg(moonSepDefault);
      setDateRanges([]);
      setNotes("");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, existingPlan, moonSepDefault]);

  useEffect(() => {
    if (locationId === "") {
      setHorizonId("");
      return;
    }
    const horizons = horizonsQuery.data;
    if (!horizons || horizons.length === 0) return;
    if (horizonId !== "" && horizons.some((h: Horizon) => h.id === horizonId)) return;
    const defaultHz = horizons.find((h: Horizon) => h.is_default);
    setHorizonId(defaultHz ? defaultHz.id : horizons[0].id);
  }, [locationId, horizonsQuery.data, horizonId]);

  const locations: Location[] = locationsQuery.data ?? [];
  const horizons: Horizon[] = horizonsQuery.data ?? [];
  const rigs: Rig[] = rigsQuery.data ?? [];
  const selectedHorizon = horizons.find((h) => h.id === horizonId);

  const canSave = locationId !== "" && horizonId !== "" && rigId !== "";

  const addDateRange = () => {
    setDateRanges((prev) => [...prev, { start_date: "", end_date: "" }]);
  };

  const updateDateRange = (idx: number, field: "start_date" | "end_date", value: string) => {
    setDateRanges((prev) => prev.map((r, i) => (i === idx ? { ...r, [field]: value } : r)));
  };

  const removeDateRange = (idx: number) => {
    setDateRanges((prev) => prev.filter((_, i) => i !== idx));
  };

  const addDateRangeFromChart = useCallback(
    (startDate: string, endDate: string) => {
      setDateRanges((prev) => {
        const next = [...prev, { start_date: startDate, end_date: endDate }];
        next.sort((a, b) => a.start_date.localeCompare(b.start_date));
        return next;
      });
    },
    [],
  );

  const autoGenerateRanges = useCallback(
    (threshold: number, points: AnnualHoursPoint[]) => {
      const ranges: DateRangeIn[] = [];
      let rangeStart: string | null = null;
      for (let i = 0; i < points.length; i++) {
        const above = points[i].hours >= threshold;
        if (above && rangeStart === null) {
          rangeStart = points[i].date;
        } else if (!above && rangeStart !== null) {
          ranges.push({ start_date: rangeStart, end_date: points[i - 1].date });
          rangeStart = null;
        }
      }
      if (rangeStart !== null) {
        ranges.push({ start_date: rangeStart, end_date: points[points.length - 1].date });
      }
      setDateRanges(ranges);
    },
    [],
  );

  const handleSave = () => {
    if (!canSave) return;
    const validRanges = dateRanges.filter((r) => r.start_date && r.end_date);

    if (existingPlan) {
      updatePlan.mutate(
        {
          planId: existingPlan.id,
          params: {
            location_id: locationId as number,
            horizon_id: horizonId as number,
            rig_id: rigId as number,
            moon_sep_deg: moonSepDeg,
            date_ranges: validRanges,
            notes: notes || null,
            clear_notes: !notes && !!existingPlan.notes,
          },
        },
        { onSuccess: onClose },
      );
    } else {
      const params: CreatePlanParams = {
        dso_id: dsoId,
        location_id: locationId as number,
        horizon_id: horizonId as number,
        rig_id: rigId as number,
        moon_sep_deg: moonSepDeg,
        date_ranges: validRanges,
      };
      if (notes) params.notes = notes;
      createPlan.mutate(params, {
        onSuccess: onClose,
        onError: (err: Error) => {
          const msg = err.message ?? "";
          if (msg.includes("409") || msg.includes("already exists")) {
            setSaveError("An assignment with this location, horizon, and rig already exists.");
          } else {
            setSaveError(msg || "Failed to create assignment.");
          }
        },
      });
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{dsoName}</DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} sx={{ mt: 1 }}>
          <Stack direction="row" gap={2}>
            <FormControl fullWidth size="small" required>
              <InputLabel>Location</InputLabel>
              <Select
                value={locationId}
                label="Location"
                onChange={(e) => setLocationId(e.target.value as number)}
              >
                {locations.map((loc) => (
                  <MenuItem key={loc.id} value={loc.id}>
                    {loc.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl fullWidth size="small" required disabled={locationId === ""}>
              <InputLabel>Horizon</InputLabel>
              <Select
                value={horizonId}
                label="Horizon"
                onChange={(e) => setHorizonId(e.target.value as number)}
              >
                {horizons.map((hz) => (
                  <MenuItem key={hz.id} value={hz.id}>
                    {hz.name}
                    {hz.type === "artificial" && hz.flat_altitude_deg != null
                      ? ` (${hz.flat_altitude_deg}°)`
                      : ""}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl fullWidth size="small" required>
              <InputLabel>Rig</InputLabel>
              <Select
                value={rigId}
                label="Rig"
                onChange={(e) => setRigId(e.target.value as number)}
              >
                {rigs.map((rig) => (
                  <MenuItem key={rig.id} value={rig.id}>
                    {rig.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>

          {locationId !== "" && horizonId !== "" && (
            <Box>
              <Stack
                direction="row"
                justifyContent="space-between"
                alignItems="center"
                sx={{ mb: 0.5 }}
              >
                <Box>
                  <Typography variant="subtitle2">Best time of year</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Hours above{" "}
                    {selectedHorizon?.type === "artificial" &&
                    selectedHorizon.flat_altitude_deg != null
                      ? `${selectedHorizon.flat_altitude_deg.toFixed(0)}°`
                      : selectedHorizon?.name ?? "horizon"}{" "}
                    during astronomical darkness. Shift-drag to select date ranges.
                  </Typography>
                </Box>
                <Stack direction="row" alignItems="center" gap={0.5} flexWrap="wrap">
                  <Checkbox
                    size="small"
                    checked={moonFilterEnabled}
                    onChange={(_, checked) => setMoonFilterEnabled(checked)}
                    sx={{ p: 0.25 }}
                  />
                  <Typography variant="caption" sx={{ color: moonFilterEnabled ? "text.primary" : "text.disabled" }}>
                    Illumination {"≤"}
                  </Typography>
                  <FormControl size="small" variant="standard" sx={{ minWidth: 60 }} disabled={!moonFilterEnabled}>
                    <Select
                      value={maxIllumination}
                      onChange={(e) => setMaxIllumination(Number(e.target.value))}
                      sx={{ fontSize: "0.8rem" }}
                    >
                      {[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100].map((v) => (
                        <MenuItem key={v} value={v}>{v}%</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl size="small" variant="standard" sx={{ minWidth: 50 }} disabled={!moonFilterEnabled}>
                    <Select
                      value={moonCombine}
                      onChange={(e) => setMoonCombine(e.target.value as "and" | "or")}
                      sx={{ fontSize: "0.8rem" }}
                    >
                      <MenuItem value="and">AND</MenuItem>
                      <MenuItem value="or">OR</MenuItem>
                    </Select>
                  </FormControl>
                  <Typography variant="caption" sx={{ color: moonFilterEnabled ? "text.primary" : "text.disabled" }}>
                    Separation {"≥"}
                  </Typography>
                  <FormControl size="small" variant="standard" sx={{ minWidth: 60 }} disabled={!moonFilterEnabled}>
                    <Select
                      value={minSeparation}
                      onChange={(e) => setMinSeparation(Number(e.target.value))}
                      sx={{ fontSize: "0.8rem" }}
                    >
                      {[0, 15, 30, 45, 60, 75, 90, 120].map((v) => (
                        <MenuItem key={v} value={v}>{v}°</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Stack>
              </Stack>

              <Box sx={{ position: "relative", minHeight: CHART_HEIGHT, overflow: "visible" }}>
                {annualHoursQuery.data && (
                  <InteractiveAnnualChart
                    track={annualHoursQuery.data}
                    dateRanges={dateRanges}
                    onAddRange={addDateRangeFromChart}
                    onRemoveRange={removeDateRange}
                    onAutoGenerate={autoGenerateRanges}
                    height={CHART_HEIGHT}
                  />
                )}
                {annualHoursQuery.isFetching && (
                  <Box
                    sx={{
                      position: "absolute",
                      inset: 0,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      bgcolor: annualHoursQuery.data ? "rgba(0, 0, 0, 0.25)" : "transparent",
                    }}
                  >
                    <CircularProgress size={24} />
                  </Box>
                )}
              </Box>
            </Box>
          )}

          {/* Date ranges — manual entry with + button */}
          <Box>
            <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 1 }}>
              <Typography variant="subtitle2">Date ranges</Typography>
              <IconButton size="small" onClick={addDateRange} aria-label="Add date range">
                <AddIcon fontSize="small" />
              </IconButton>
            </Stack>
            {dateRanges.length === 0 ? (
              <Typography variant="caption" color="text.secondary">
                No date ranges. Use the + button or shift-drag on the chart above.
              </Typography>
            ) : (
              <Stack gap={1}>
                {dateRanges.map((range, idx) => (
                  <Stack key={idx} direction="row" gap={1} alignItems="center">
                    <TextField
                      label="Start"
                      type="date"
                      size="small"
                      fullWidth
                      slotProps={{ inputLabel: { shrink: true } }}
                      value={range.start_date}
                      onChange={(e) => updateDateRange(idx, "start_date", e.target.value)}
                    />
                    <TextField
                      label="End"
                      type="date"
                      size="small"
                      fullWidth
                      slotProps={{ inputLabel: { shrink: true } }}
                      value={range.end_date}
                      onChange={(e) => updateDateRange(idx, "end_date", e.target.value)}
                    />
                    <IconButton
                      size="small"
                      onClick={() => removeDateRange(idx)}
                      aria-label="Remove date range"
                    >
                      <CloseIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                ))}
              </Stack>
            )}
          </Box>

          <TextField
            label="Notes"
            size="small"
            fullWidth
            multiline
            minRows={2}
            maxRows={4}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g., need 20h Ha+OIII, broadband on moonlit nights"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        {saveError && (
          <Typography variant="caption" color="error" sx={{ flex: 1, ml: 2 }}>
            {saveError}
          </Typography>
        )}
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => { setSaveError(null); handleSave(); }}
          disabled={!canSave || createPlan.isPending || updatePlan.isPending}
        >
          {existingPlan ? "Save" : "Create"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}


// ── Interactive annual hours chart with range selection ──────────────────────

function InteractiveAnnualChart({
  track,
  dateRanges,
  onAddRange,
  onRemoveRange,
  onAutoGenerate,
  height,
}: {
  track: AnnualHoursResponse;
  dateRanges: DateRangeIn[];
  onAddRange: (start: string, end: string) => void;
  onRemoveRange: (idx: number) => void;
  onAutoGenerate: (threshold: number, points: AnnualHoursPoint[]) => void;
  height: number;
}) {
  const theme = useTheme();
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [width, setWidth] = useState(600);
  const [dragStart, setDragStart] = useState<number | null>(null);
  const [dragEnd, setDragEnd] = useState<number | null>(null);
  const [thresholdHours, setThresholdHours] = useState(2.0);
  const [hover, setHover] = useState<{
    xPx: number;
    yPx: number;
    dateLabel: string;
    hours: number;
    illuminationPct: number | null;
    minSeparationDeg: number | null;
    isSnapped: boolean;
  } | null>(null);

  const isDark = theme.palette.mode === "dark";
  const pts = track.points;
  const wPts = track.filtered_points ?? [];
  const moonIllum = track.moon_data ?? [];
  const hasWeighted = wPts.length > 0 && wPts.some((p, i) => Math.abs(p.hours - pts[i]?.hours) > 0.01);
  const activePts = hasWeighted ? wPts : pts;

  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const obs = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const innerW = width - CHART_MARGIN.left - CHART_MARGIN.right;
  const innerH = height - CHART_MARGIN.top - CHART_MARGIN.bottom;

  const xScale = d3
    .scaleTime()
    .domain([new Date(pts[0].date), new Date(pts[pts.length - 1].date)])
    .range([0, innerW]);

  const maxH = Math.ceil(Math.max(
    d3.max(pts, (d) => d.hours) ?? 1,
    d3.max(wPts, (d) => d.hours) ?? 0,
  ));
  const yScale = d3
    .scaleLinear()
    .domain([0, Math.max(maxH, 1)])
    .range([innerH, 0]);

  const line = d3
    .line<AnnualHoursPoint>()
    .x((d) => xScale(new Date(d.date)))
    .y((d) => yScale(d.hours))
    .curve(d3.curveMonotoneX);

  const pathD = line(pts) ?? "";
  const weightedPathD = hasWeighted ? (line(wPts) ?? "") : "";

  const SNAP_PX = 8;

  const crossingXPositions = useMemo(() => {
    const crossings: number[] = [];
    for (let i = 1; i < activePts.length; i++) {
      const prev = activePts[i - 1].hours;
      const curr = activePts[i].hours;
      if ((prev < thresholdHours && curr >= thresholdHours) ||
          (prev >= thresholdHours && curr < thresholdHours)) {
        const t = (thresholdHours - prev) / (curr - prev);
        const d0 = new Date(activePts[i - 1].date).getTime();
        const d1 = new Date(activePts[i].date).getTime();
        crossings.push(xScale(new Date(d0 + t * (d1 - d0))));
      }
    }
    crossings.sort((a, b) => a - b);
    return [...new Set(crossings.map((c) => Math.round(c * 10) / 10))];
  }, [activePts, thresholdHours, xScale]);

  const dateFromX = (px: number): string => {
    const d = xScale.invert(px - CHART_MARGIN.left);
    return d.toISOString().slice(0, 10);
  };

  const formatDateLabel = (d: Date): string =>
    d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

  const hoursAtX = (x: number): { hours: number; idx: number } => {
    const t = xScale.invert(x);
    const idx = Math.max(0, Math.min(activePts.length - 1,
      d3.bisector((p: AnnualHoursPoint) => new Date(p.date)).left(activePts, t)));
    return { hours: activePts[idx].hours, idx };
  };

  const snapToNearestCrossing = (rawX: number): number => {
    let best = rawX;
    for (const cx of crossingXPositions) {
      if (Math.abs(rawX - cx) <= SNAP_PX) {
        best = cx;
        break;
      }
    }
    return best;
  };

  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!e.shiftKey) return;
    const rect = svgRef.current!.getBoundingClientRect();
    const rawX = e.clientX - rect.left - CHART_MARGIN.left;
    if (rawX < 0 || rawX > innerW) return;
    const x = snapToNearestCrossing(rawX);
    setDragStart(x);
    setDragEnd(x);
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = svgRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left - CHART_MARGIN.left;

    if (dragStart !== null) {
      const clamped = Math.max(0, Math.min(innerW, mx));
      setDragEnd(snapToNearestCrossing(clamped));
      setHover(null);
      return;
    }

    if (mx < 0 || mx > innerW) {
      setHover(null);
      return;
    }

    let snapX = mx;
    let isSnapped = false;
    for (const cx of crossingXPositions) {
      if (Math.abs(mx - cx) <= SNAP_PX) {
        snapX = cx;
        isSnapped = true;
        break;
      }
    }

    const { hours, idx } = hoursAtX(snapX);
    const dateAtPos = isSnapped
      ? xScale.invert(snapX)
      : new Date(activePts[idx].date);

    setHover({
      xPx: snapX,
      yPx: yScale(hours),
      dateLabel: formatDateLabel(dateAtPos),
      hours,
      illuminationPct: moonIllum[idx]?.illumination_pct ?? null,
      minSeparationDeg: moonIllum[idx]?.min_separation_deg ?? null,
      isSnapped,
    });
  };

  const handleMouseUp = () => {
    if (dragStart === null || dragEnd === null) {
      setDragStart(null);
      setDragEnd(null);
      return;
    }
    const x1 = Math.min(dragStart, dragEnd);
    const x2 = Math.max(dragStart, dragEnd);
    if (x2 - x1 < 5) {
      setDragStart(null);
      setDragEnd(null);
      return;
    }
    const startDate = dateFromX(x1 + CHART_MARGIN.left);
    const endDate = dateFromX(x2 + CHART_MARGIN.left);

    const overlaps = dateRanges.some(
      (r) => r.start_date && r.end_date && startDate <= r.end_date && endDate >= r.start_date,
    );
    if (!overlaps) {
      onAddRange(startDate, endDate);
    }

    setDragStart(null);
    setDragEnd(null);
  };

  const handleThresholdDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const svg = svgRef.current!;

    const snapTo30Min = (raw: number) => Math.max(0, Math.round(raw * 2) / 2);

    const onMove = (ev: MouseEvent) => {
      const rect = svg.getBoundingClientRect();
      const y = ev.clientY - rect.top - CHART_MARGIN.top;
      const hours = yScale.invert(Math.max(0, Math.min(innerH, y)));
      setThresholdHours(snapTo30Min(hours));
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  const rangeColor = `${RIG_ORANGE}55`;
  const dragColor = isDark ? "rgba(255, 255, 255, 0.15)" : "rgba(0, 0, 0, 0.08)";
  const threshColor = isDark ? "#ffffff66" : "#00000044";
  const todayX = xScale(new Date());

  return (
    <Box ref={wrapperRef} sx={{ width: "100%", userSelect: "none", position: "relative" }}>
      <svg
        ref={svgRef}
        width={width}
        height={height}
        style={{ display: "block", cursor: "crosshair" }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => { handleMouseUp(); setHover(null); }}
      >
        <g transform={`translate(${CHART_MARGIN.left},${CHART_MARGIN.top})`}>
          {/* Date range rectangles */}
          {dateRanges.map((r, idx) => {
            if (!r.start_date || !r.end_date) return null;
            const x1 = xScale(new Date(r.start_date));
            const x2 = xScale(new Date(r.end_date));
            return (
              <g key={idx}>
                <rect
                  x={x1}
                  y={0}
                  width={Math.max(2, x2 - x1)}
                  height={innerH}
                  fill={rangeColor}
                />
                {/* Close button */}
                <g
                  transform={`translate(${x2 - 8}, 4)`}
                  style={{ cursor: "pointer" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemoveRange(idx);
                  }}
                >
                  <circle r={7} fill={isDark ? "#333333" : "#eeeeee"} stroke={isDark ? "#666666" : "#999999"} strokeWidth={0.5} />
                  <line x1={-3} y1={-3} x2={3} y2={3} stroke={isDark ? "#cccccc" : "#444444"} strokeWidth={1.5} />
                  <line x1={3} y1={-3} x2={-3} y2={3} stroke={isDark ? "#cccccc" : "#444444"} strokeWidth={1.5} />
                </g>
              </g>
            );
          })}

          {/* Drag preview */}
          {dragStart !== null && dragEnd !== null && (
            <rect
              x={Math.min(dragStart, dragEnd)}
              y={0}
              width={Math.abs(dragEnd - dragStart)}
              height={innerH}
              fill={dragColor}
              stroke={isDark ? "#ffffff44" : "#00000022"}
              strokeDasharray="4,2"
            />
          )}

          {/* Moon phase backdrop */}
          {moonIllum.length > 0 && moonIllum.map((m, i) => {
            if (i >= pts.length) return null;
            const xPos = xScale(new Date(pts[i].date));
            const nextX = i + 1 < pts.length ? xScale(new Date(pts[i + 1].date)) : xPos + 1;
            const opacity = isDark
              ? 0.02 + (m.illumination_pct / 100) * 0.06
              : 0.01 + (m.illumination_pct / 100) * 0.04;
            return (
              <rect
                key={`moon-${i}`}
                x={xPos}
                y={0}
                width={Math.max(0.5, nextX - xPos)}
                height={innerH}
                fill={isDark ? "#ffffff" : "#000000"}
                opacity={opacity}
              />
            );
          })}

          {/* Hours curve — filtered (orange) when moon filter active, raw (blue) otherwise */}
          {hasWeighted ? (
            <path d={weightedPathD} fill="none" stroke={RIG_ORANGE} strokeWidth={2} />
          ) : (
            <path d={pathD} fill="none" stroke={RIG_BLUE} strokeWidth={1.5} />
          )}

          {/* Today line */}
          {todayX >= 0 && todayX <= innerW && (
            <line
              x1={todayX}
              y1={0}
              x2={todayX}
              y2={innerH}
              stroke={threshColor}
              strokeWidth={1}
              strokeDasharray="4,3"
            />
          )}

          {/* Hours threshold line — always visible, extends into right margin */}
          <line
            x1={0}
            y1={yScale(thresholdHours)}
            x2={innerW + HANDLE_SIZE + 4}
            y2={yScale(thresholdHours)}
            stroke={RIG_ORANGE}
            strokeWidth={1.5}
            strokeDasharray="6,3"
            style={{ cursor: "ns-resize" }}
            onMouseDown={handleThresholdDrag}
          />
          {/* Drag handle — squeeze arrows icon */}
          <g
            transform={`translate(${innerW + HANDLE_SIZE / 2 + 4}, ${yScale(thresholdHours)})`}
            style={{ cursor: "ns-resize" }}
            onMouseDown={handleThresholdDrag}
          >
            <rect
              x={-HANDLE_SIZE / 2}
              y={-HANDLE_SIZE / 2}
              width={HANDLE_SIZE}
              height={HANDLE_SIZE}
              fill="transparent"
            />
            {/* Up arrow */}
            <path
              d="M0,-10 L4,-5 L1,-5 L1,-2 L-1,-2 L-1,-5 L-4,-5 Z"
              fill={RIG_ORANGE}
            />
            {/* Down arrow */}
            <path
              d="M0,10 L4,5 L1,5 L1,2 L-1,2 L-1,5 L-4,5 Z"
              fill={RIG_ORANGE}
            />
          </g>
          <text
            x={innerW + HANDLE_SIZE / 2 + 4}
            y={yScale(thresholdHours) - HANDLE_SIZE / 2 - 2}
            textAnchor="middle"
            fill={RIG_ORANGE}
            fontSize={10}
            fontWeight={600}
          >
            {thresholdHours.toFixed(1)}h
          </text>

          {/* X axis */}
          {xScale.ticks(d3.timeMonth.every(1)!).map((d) => (
            <g key={d.getTime()} transform={`translate(${xScale(d)},${innerH})`}>
              <line y2={4} stroke={isDark ? "#555555" : "#cccccc"} />
              <text
                y={16}
                textAnchor="middle"
                fill={isDark ? "#999999" : "#666666"}
                fontSize={9}
              >
                {d.toLocaleDateString("en", { month: "short" })}
              </text>
            </g>
          ))}

          {/* Y axis grid + labels */}
          {yScale.ticks(5).map((h) => (
            <g key={h} transform={`translate(0,${yScale(h)})`}>
              <line x2={innerW} stroke={isDark ? "#333333" : "#eeeeee"} strokeWidth={0.5} />
              <text
                x={-6}
                textAnchor="end"
                dominantBaseline="middle"
                fill={isDark ? "#888888" : "#888888"}
                fontSize={9}
              >
                {h}h
              </text>
            </g>
          ))}

          {/* Chart border — top and bottom edges */}
          <line x1={0} y1={0} x2={innerW} y2={0} stroke={isDark ? "#555555" : "#cccccc"} strokeWidth={1} />
          <line x1={0} y1={innerH} x2={innerW} y2={innerH} stroke={isDark ? "#555555" : "#cccccc"} strokeWidth={1} />
          {/* Top label — max hours */}
          <text
            x={-6}
            y={0}
            textAnchor="end"
            dominantBaseline="middle"
            fill={isDark ? "#aaaaaa" : "#666666"}
            fontSize={9}
            fontWeight={600}
          >
            {yScale.domain()[1]}h
          </text>

          {/* Threshold crossing markers */}
          {crossingXPositions.map((cx: number, i: number) => (
            <circle
              key={i}
              cx={cx}
              cy={yScale(thresholdHours)}
              r={3}
              fill={RIG_ORANGE}
              stroke={isDark ? "#000000" : "#ffffff"}
              strokeWidth={1}
            />
          ))}

          {/* Hover crosshair */}
          {hover && !dragStart && (
            <>
              <line
                x1={hover.xPx}
                x2={hover.xPx}
                y1={0}
                y2={innerH}
                stroke={isDark ? "#aaaaaa" : "#666666"}
                strokeWidth={1}
                strokeDasharray="2,2"
                pointerEvents="none"
              />
              <circle
                cx={hover.xPx}
                cy={hover.yPx}
                r={hover.isSnapped ? 5 : 3.5}
                fill={hasWeighted ? RIG_ORANGE : RIG_BLUE}
                stroke={isDark ? "#000000" : "#ffffff"}
                strokeWidth={1.5}
                pointerEvents="none"
              />
            </>
          )}
        </g>
      </svg>

      {/* Auto-generate button */}
      <Box sx={{ display: "flex", justifyContent: "flex-end", mt: 0.5 }}>
        <Tooltip
          title={`Replace all date ranges with periods where ${hasWeighted ? "effective" : "raw"} hours ≥ ${thresholdHours.toFixed(1)}h`}
          arrow
          placement="left"
        >
          <Button
            size="small"
            variant="outlined"
            onClick={() => onAutoGenerate(thresholdHours, activePts)}
            sx={{ textTransform: "none", fontSize: "0.75rem" }}
          >
            Auto from {thresholdHours.toFixed(1)}h
          </Button>
        </Tooltip>
      </Box>

      {/* Hover tooltip — positioned above the chart */}
      {hover && !dragStart && (
        <Box
          sx={{
            position: "absolute",
            top: -40,
            left: Math.min(
              hover.xPx + CHART_MARGIN.left + 10,
              width - 160,
            ),
            bgcolor: "background.paper",
            border: 1,
            borderColor: "divider",
            borderRadius: 1,
            px: 1,
            py: 0.5,
            pointerEvents: "none",
            fontSize: 12,
            lineHeight: 1.4,
            minWidth: 120,
            boxShadow: 2,
            zIndex: 1,
          }}
        >
          <Typography variant="caption" fontWeight={600}>
            {hover.dateLabel}
          </Typography>
          <Box sx={{ color: hasWeighted ? RIG_ORANGE : RIG_BLUE }}>
            {hover.hours.toFixed(1)} h{hasWeighted ? " effective" : ""}
          </Box>
          {(hover.illuminationPct != null || hover.minSeparationDeg != null) && (
            <Box sx={{ color: "text.secondary", fontSize: 11 }}>
              Moon: {hover.illuminationPct != null ? `${hover.illuminationPct.toFixed(0)}%` : "—"}
              {hover.minSeparationDeg != null ? ` · ${hover.minSeparationDeg.toFixed(0)}° sep` : ""}
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}
