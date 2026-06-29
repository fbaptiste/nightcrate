/**
 * Planner detail panel — larger thumbnail + sky-position graph + metadata.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  fetchAnnualHours,
  fetchSkyTrack,
  type PlannerTargetItem,
} from "@/api/planner";
import { fetchDso } from "@/api/dsos";
import { fetchHorizons, type Horizon } from "@/api/horizons";
import { fetchSingleTargetScore } from "@/api/planner";
import { type Rig } from "@/api/rigs";
import { type Location } from "@/api/locations";
import { usePlannerStore } from "@/stores/plannerStore";
import { displayConstellation } from "@/lib/constellations";
import { formatDistance } from "@/lib/distanceFormat";
import { displayDsoType, dsoTypeColor } from "@/lib/dsoTypeNames";
import { DsoExternalRefs } from "@/components/dso/DsoExternalRefs";
import SkyPreview from "@/components/dso/SkyPreview";
import BestTimeOfYearChart from "./BestTimeOfYearChart";
import MoonFilterControls from "./MoonFilterControls";
import { ScoreBreakdownSection } from "./ScoreBreakdownSection";
import { ScoreChip } from "./ScoreChip";
import SkyPositionView from "./SkyPositionView";
import FovSimulator from "./FovSimulator";
import { renderHorizonMenuItems } from "./horizonMenuItems";

interface Props {
  dsoId: number | null;
  target: PlannerTargetItem | null;
  /** Location the parent page has selected — the preview dropdown
   *  starts from this value. Panel-local overrides NEVER propagate
   *  back to the parent (grid stays on the parent's choice). */
  selectedLocationId: number | null;
  locations: Location[];
  /** Horizon the parent page has selected — the preview dropdown
   *  starts from this value. Resets to the preview location's
   *  default whenever the user swaps previewed locations. */
  selectedHorizonId: number | null;
  /** Rig the parent page has selected — the preview dropdown starts
   *  from this value. Panel-local overrides NEVER propagate back to
   *  the parent (grid stays on the parent's choice). */
  selectedRigId: number | null;
  /** Full rig list for the dropdown. */
  rigs: Rig[];
  /** Swap the dialog to a different DSO (triggered by the FOV
   *  simulator's annotation popover's "Show details" button). The
   *  dialog stays open; rig / location selections persist. */
  onSelectDso?: (dsoId: number) => void;
  onClose: () => void;
}

/** Null-safe variant — renders ``—`` for null/invalid ISO strings.
 *  Same shape as ``formatLocalTime`` in ``PlannerPage`` /
 *  ``PlannerTargetCard``; keep the name in step across the three
 *  files. */
function formatLocalTime(iso: string | null, tz: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: tz,
    });
  } catch {
    return "—";
  }
}

// Small helper — renders one `Label · Value` pair in the metadata grid
// as a single inline row so the fact list stays compact vertically.
// An optional ``help`` string attaches a tooltip to the label for
// facts whose one-word title can't fully convey what they mean.
function Fact({
  label,
  value,
  help,
}: {
  label: string;
  value: React.ReactNode;
  help?: string;
}) {
  const labelEl = (
    <Box
      component="span"
      sx={{
        color: "text.secondary",
        textTransform: "uppercase",
        letterSpacing: 0.4,
        fontSize: "0.65rem",
        mr: 1,
        // Slight dotted underline hint when a tooltip is attached,
        // so users know the label is worth hovering.
        textDecoration: help ? "underline dotted" : undefined,
        textUnderlineOffset: help ? "2px" : undefined,
        cursor: help ? "help" : undefined,
      }}
    >
      {label}
    </Box>
  );
  return (
    <Typography variant="body2" sx={{ lineHeight: 1.5 }}>
      {help ? (
        <Tooltip title={help} arrow placement="top">
          {labelEl}
        </Tooltip>
      ) : (
        labelEl
      )}
      {value}
    </Typography>
  );
}

export default function PlannerDetailPanel({
  dsoId,
  target,
  selectedLocationId,
  locations,
  selectedHorizonId,
  selectedRigId,
  rigs,
  onSelectDso,
  onClose,
}: Props) {
  const detailTheme = useTheme();
  const isNarrow = useMediaQuery(detailTheme.breakpoints.down("md"));

  // Local preview overrides — distinct from the parent's
  // ``selectedLocationId``, ``selectedHorizonId``, and ``selectedRigId``.
  // Changing any only affects what the panel renders (sky track +
  // simulator + fact grid + coverage narrative). Each resets back to
  // the parent's choice on target open.
  const [previewLocationId, setPreviewLocationId] = useState<number | null>(
    selectedLocationId,
  );
  const [previewHorizonId, setPreviewHorizonId] = useState<number | null>(
    selectedHorizonId,
  );
  const [previewRigId, setPreviewRigId] = useState<number | null>(selectedRigId);
  useEffect(() => {
    if (dsoId != null) {
      setPreviewLocationId(selectedLocationId);
      setPreviewHorizonId(selectedHorizonId);
      setPreviewRigId(selectedRigId);
    }
  }, [dsoId, selectedLocationId, selectedHorizonId, selectedRigId]);

  const previewLocation = locations.find((l) => l.id === previewLocationId) ?? null;
  const tz = previewLocation?.timezone ?? "UTC";

  const dsoQuery = useQuery({
    queryKey: ["dso", dsoId],
    queryFn: () => fetchDso(dsoId as number),
    enabled: dsoId != null,
  });

  // Load horizons for the previewed location. Whenever the previewed
  // location changes we reset the horizon override to that location's
  // default so the sky-track and chart queries don't fire against a
  // horizon from the wrong location.
  const horizonsQuery = useQuery({
    queryKey: ["horizons", previewLocationId],
    queryFn: () => fetchHorizons(previewLocationId as number),
    enabled: previewLocationId != null,
    staleTime: 60 * 60 * 1000,
  });
  const horizons: Horizon[] = horizonsQuery.data ?? [];
  const defaultHorizon = horizons.find((h) => h.is_default) ?? null;

  useEffect(() => {
    // When the previewed location changes, snap to that location's
    // default horizon — selectedHorizonId from the parent might
    // belong to a different location.
    if (previewLocationId == null) return;
    if (horizons.length === 0) return;
    const valid = horizons.some((h) => h.id === previewHorizonId);
    if (!valid) {
      setPreviewHorizonId(defaultHorizon?.id ?? null);
    }
  }, [previewLocationId, horizons, defaultHorizon, previewHorizonId]);

  const effectiveHorizon =
    horizons.find((h) => h.id === previewHorizonId) ?? defaultHorizon;

  const skyTrackQuery = useQuery({
    queryKey: ["sky-track", dsoId, previewLocationId, effectiveHorizon?.id ?? null],
    queryFn: () =>
      fetchSkyTrack(
        dsoId as number,
        previewLocationId as number,
        effectiveHorizon?.id ?? null,
      ),
    enabled:
      dsoId != null && previewLocationId != null && effectiveHorizon != null,
  });

  // Panel-local scoring. The list-fetch score on ``target`` is frozen
  // on the page's rig / horizon / location — when any of those are
  // overridden in the panel, that score goes stale. This query
  // recomputes against the preview state so the breakdown section
  // always reflects what the user is currently previewing.
  const filterIntent = usePlannerStore((s) => s.filterIntent);
  const previewScoreQuery = useQuery({
    queryKey: [
      "target-score",
      dsoId,
      previewLocationId,
      effectiveHorizon?.id ?? null,
      previewRigId,
      filterIntent,
    ],
    queryFn: () =>
      fetchSingleTargetScore(dsoId as number, {
        locationId: previewLocationId as number,
        horizonId: effectiveHorizon?.id ?? null,
        rigId: previewRigId,
        filterIntent,
      }),
    enabled:
      dsoId != null && previewLocationId != null && effectiveHorizon != null,
  });

  // "Best time of year" controls — moon-separation dropdown only now
  // (horizon threshold comes from the dedicated horizon selector).
  const [moonFilterEnabled, setMoonFilterEnabled] = useState(false);
  const [maxIllumination, setMaxIllumination] = useState<number>(50);
  const [minSeparation, setMinSeparation] = useState<number>(60);
  const [moonCombine, setMoonCombine] = useState<"and" | "or">("and");
  const [skyPosOpen, setSkyPosOpen] = useState(true);
  const [bestTimeOpen, setBestTimeOpen] = useState(true);
  const [scoreOpen, setScoreOpen] = useState(false);

  // Annual "best time of year" track. First-load compute is a few
  // seconds (full-year 5-min astropy grid on cold cache); TanStack
  // caches per (dso, location, horizon, moon_sep_deg) for an hour so
  // user-driven churn stays mostly cheap.
  const annualHoursQuery = useQuery({
    queryKey: [
      "annual-hours",
      dsoId,
      previewLocationId,
      effectiveHorizon?.id ?? null,
      moonFilterEnabled,
      maxIllumination,
      minSeparation,
      moonCombine,
    ],
    queryFn: () =>
      fetchAnnualHours(dsoId as number, previewLocationId as number, {
        horizonId: effectiveHorizon?.id,
        moonSepDeg: 0,
        includeMoon: true, // chart draws the Moon-altitude line + illumination
        maxIlluminationPct: moonFilterEnabled ? maxIllumination : undefined,
        minSeparationDeg: moonFilterEnabled ? minSeparation : undefined,
        moonCombine: moonFilterEnabled ? moonCombine : undefined,
      }),
    enabled:
      dsoId != null && previewLocationId != null && effectiveHorizon != null,
    staleTime: 60 * 60 * 1000,
  });

  const open = dsoId != null;
  const dso = dsoQuery.data;

  // Visibility facts + score source. Prefer the per-DSO score fetch (always
  // for the current dsoId + preview context); fall back to the list row while
  // it loads. Using the fetch means the fact grid + Score still render when
  // the object isn't in the loaded list page (e.g. switched via the FOV
  // annotation), and stays consistent with any panel rig/horizon override.
  const facts = previewScoreQuery.data ?? target;

  // Derive [major, minor] FOV (sorted) and name from the preview rig —
  // ``Rig.calculators.field_of_view_deg`` is raw (width, height) from
  // the sensor, not sorted. The simulator expects major/minor.
  const previewRig = rigs.find((r) => r.id === previewRigId) ?? null;
  const rigFov: [number, number] | null = previewRig
    ? (() => {
        const [w, h] = previewRig.calculators.field_of_view_deg;
        return [Math.max(w, h), Math.min(w, h)];
      })()
    : null;

  const coveragePct =
    rigFov && dso?.maj_axis_arcmin
      ? (() => {
          const objMaj = dso.maj_axis_arcmin! / 60;
          const objMin = (dso.min_axis_arcmin ?? dso.maj_axis_arcmin!) / 60;
          return Math.max((objMaj / rigFov[0]) * 100, (objMin / rigFov[1]) * 100);
        })()
      : null;

  const distance = formatDistance(dso?.distance_pc);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" fullScreen={isNarrow}>
      <DialogTitle sx={{ display: "flex", alignItems: "flex-start", gap: 2, py: 1.25 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {/* Title row: primary designation + constellation. Distance
              moved to the fact grid below so the header stays focused
              on identifiers (name + cross-refs + type). */}
          <Stack direction="row" gap={1.5} alignItems="baseline" flexWrap="wrap">
            <Typography variant="h6">{dso?.primary_designation ?? "…"}</Typography>
            {dso?.constellation && (
              <Typography variant="body2" color="text.secondary">
                {displayConstellation(dso.constellation)}
              </Typography>
            )}
          </Stack>

          {dso?.common_name && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
              {dso.common_name}
            </Typography>
          )}

          {/* Type pill + alternate catalog designations — one line
              describing "what kind of object, and what else it's
              called". Primary designation is already the title, so
              only alternates are listed here (no redundant M 42 chip
              when "M 42" is the heading). */}
          {dso && (dso.obj_type || dso.designations.length > 0) && (
            <Stack
              direction="row"
              flexWrap="wrap"
              gap={0.75}
              alignItems="center"
              sx={{ mt: 0.75 }}
            >
              {dso.obj_type && (
                <Chip
                  label={displayDsoType(dso.obj_type)}
                  size="small"
                  sx={{
                    bgcolor: dsoTypeColor(dso.obj_type),
                    color: "#ffffff",
                    fontWeight: 500,
                  }}
                />
              )}
              {dso.designations
                .filter((d) => !d.is_primary)
                .map((d) => (
                  <Chip
                    key={`${d.catalog}-${d.identifier}`}
                    label={d.display_form}
                    size="small"
                    variant="outlined"
                  />
                ))}
            </Stack>
          )}

          {/* External refs (Wikipedia / SIMBAD / NED). Wikidata is
              filtered out inside ``DsoExternalRefs``. */}
          {dso && (
            <Box sx={{ mt: 0.75 }}>
              <DsoExternalRefs refs={dso.external_refs} title="" />
            </Box>
          )}
        </Box>
        <Stack
          direction="column"
          gap={0.5}
          alignItems="flex-end"
          sx={{ lineHeight: 1.3 }}
        >
          {locations.length > 0 && (
            <Stack direction="row" gap={0.75} alignItems="center">
              <Typography variant="caption" color="text.secondary">
                Location
              </Typography>
              <FormControl size="small" variant="standard" sx={{ minWidth: 140 }}>
                <Select
                  value={previewLocationId ?? ""}
                  onChange={(e) => {
                    const v = String(e.target.value);
                    setPreviewLocationId(v === "" ? null : Number(v));
                    // Drop the horizon override — the new location
                    // resolves its own default.
                    setPreviewHorizonId(null);
                  }}
                  sx={{ fontSize: "0.75rem" }}
                >
                  {locations.map((l) => (
                    <MenuItem key={l.id} value={l.id}>
                      {l.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Stack>
          )}
          {previewLocationId != null && horizons.length > 0 && (
            <Stack direction="row" gap={0.75} alignItems="center">
              <Typography variant="caption" color="text.secondary">
                Horizon
              </Typography>
              <FormControl size="small" variant="standard" sx={{ minWidth: 140 }}>
                <Select
                  value={effectiveHorizon?.id ?? ""}
                  onChange={(e) => setPreviewHorizonId(Number(e.target.value))}
                  sx={{ fontSize: "0.75rem" }}
                >
                  {renderHorizonMenuItems(horizons)}
                </Select>
              </FormControl>
            </Stack>
          )}
          {rigs.length > 0 && (
            <Stack direction="row" gap={0.75} alignItems="center">
              <Typography variant="caption" color="text.secondary">
                Rig
              </Typography>
              <FormControl size="small" variant="standard" sx={{ minWidth: 140 }}>
                <Select
                  value={previewRigId ?? ""}
                  onChange={(e) => {
                    const v = String(e.target.value);
                    setPreviewRigId(v === "" ? null : Number(v));
                  }}
                  sx={{ fontSize: "0.75rem" }}
                >
                  <MenuItem value="">
                    <em>No rig</em>
                  </MenuItem>
                  {rigs.map((r) => (
                    <MenuItem key={r.id} value={r.id}>
                      {r.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Stack>
          )}
        </Stack>
        <IconButton size="small" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {/* Hero region: FOV Simulator when a rig is selected (the sensor
            rectangle overlays a wide-view DSS2 image the user can rotate);
            otherwise the plain detail-variant thumbnail. */}
        {dsoId != null && rigFov ? (
          // ``key`` forces a full remount when the DSO or rig changes.
          // Without it, React re-renders the same instance with the
          // new ``dsoId`` while ``gridN`` is still 5 from the previous
          // target — the first render mounts 25 ThumbnailCells (one
          // per tile in the old grid), each firing a CDS fetch
          // **before** the reset useEffect can drop gridN back to 1.
          // That's the "18 s wait with neighbours landing before the
          // centre" path. Remounting guarantees gridN starts at 1 and
          // only the centre tile makes a network request up front.
          <FovSimulator
            key={`${dsoId}:${rigFov[0]}:${rigFov[1]}`}
            dsoId={dsoId}
            fovMajorDeg={rigFov[0]}
            fovMinorDeg={rigFov[1]}
            dsoMajAxisArcmin={dso?.maj_axis_arcmin ?? null}
            centerRaDeg={dso?.ra_deg ?? null}
            centerDecDeg={dso?.dec_deg ?? null}
            primaryDesignation={dso?.primary_designation ?? null}
            onSelectDso={onSelectDso}
            size={560}
          />
        ) : dsoId != null && dso?.ra_deg != null && dso?.dec_deg != null ? (
          // No rig selected — fall back to the same auto-tier
          // ``SkyPreview`` the DSO Catalog detail uses. Zooms to fit
          // the DSO's angular size (wider for small targets, tighter
          // for bright nebulae) and shares the sky-tile cache with
          // the rig-mode simulator.
          <Box
            sx={{
              mx: "auto",
              maxWidth: 560,
              aspectRatio: "1 / 1",
              width: "100%",
              bgcolor: "#000000",
              position: "relative",
            }}
          >
            <SkyPreview
              raDeg={dso.ra_deg}
              decDeg={dso.dec_deg}
              majAxisArcmin={dso.maj_axis_arcmin ?? null}
            />
          </Box>
        ) : null}

        {/* Scale row — pixel scale, image scale, FOV — only when a rig
            is chosen. Single caption line, ``·``-separated. Gives the
            user the same four facts MOST imaging sessions are planned
            around without making them click through to the rig page. */}
        {previewRig && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ mt: 1.5, display: "block" }}
          >
            Pixel scale {previewRig.pixel_size_um.toFixed(2)} μm · Image scale{" "}
            {previewRig.calculators.image_scale_arcsec_per_pixel.toFixed(2)}{" "}
            &quot;/px · FOV{" "}
            {previewRig.calculators.field_of_view_deg[0].toFixed(2)}° ×{" "}
            {previewRig.calculators.field_of_view_deg[1].toFixed(2)}°
          </Typography>
        )}

        {/* Designation pills + Wikipedia chip now live in the header
            next to the type/distance chips (search this file for
            ``dso.designations.map``). */}

        {/* Fact grid — three explicit rows with semantic grouping:
              Row 1: physical/imaging-framing facts (distance, size,
                     FOV coverage when a rig is selected).
              Row 2: tonight-visibility facts (hours, max altitude,
                     meridian transit, moon separation).
              Row 3: photometry (Mag V, Mag B). Low priority, on its
                     own line so it doesn't crowd the more-often-
                     consulted rows above.

            Flex + wrap handles narrow screens; each row's items pack
            left-aligned with a consistent gap. The FOV coverage cell
            is rendered unconditionally so row 1 keeps three columns
            whether or not a rig is selected (shows "—" when absent).
            The "This object fits comfortably…" narrative that used
            to live here was removed — users can see the framing in
            the simulator above; the sentence duplicated that signal. */}
        <Stack spacing={0.75} sx={{ mt: 1.5 }}>
          <Stack direction="row" gap={3} flexWrap="wrap">
            <Fact
              label="Distance"
              value={distance ? `${distance.primary} · ${distance.secondary}` : "—"}
            />
            <Fact
              label="Size"
              value={
                dso?.maj_axis_arcmin
                  ? `${dso.maj_axis_arcmin.toFixed(1)}' × ${(
                      dso.min_axis_arcmin ?? dso.maj_axis_arcmin
                    ).toFixed(1)}'`
                  : "—"
              }
            />
            <Fact
              label="FOV coverage"
              value={
                rigFov && coveragePct != null
                  ? `${coveragePct.toFixed(0)}%`
                  : "—"
              }
            />
          </Stack>
          <Stack direction="row" gap={3} flexWrap="wrap">
            <Fact
              label="Hours visible"
              value={
                facts?.hours_visible != null
                  ? `${facts.hours_visible.toFixed(1)} h`
                  : "—"
              }
            />
            <Fact
              label="Max alt. in dark"
              help={
                "Highest altitude the target reaches during astronomical darkness (sun below −18°). " +
                "If the target transits during twilight or daylight, the true transit altitude may be " +
                "higher — see the Meridian row for that."
              }
              value={
                facts?.max_altitude_deg != null && facts.peak_time_utc != null
                  ? `${facts.max_altitude_deg.toFixed(0)}° @ ${formatLocalTime(
                      facts.peak_time_utc,
                      tz,
                    )}`
                  : "—"
              }
            />
            <Fact
              label="Meridian"
              value={
                facts?.altitude_at_transit_deg != null &&
                facts.transit_time_utc != null
                  ? `${facts.altitude_at_transit_deg.toFixed(0)}° @ ${formatLocalTime(
                      facts.transit_time_utc,
                      tz,
                    )}`
                  : "—"
              }
            />
            <Fact
              label="Moon separation"
              value={
                facts?.min_moon_separation_deg != null
                  ? `${facts.min_moon_separation_deg.toFixed(0)}°`
                  : "—"
              }
            />
            <Fact
              label="Moon illumination"
              value={
                skyTrackQuery.data?.moon_phase_pct != null
                  ? `${Math.round(skyTrackQuery.data.moon_phase_pct)}%`
                  : "—"
              }
            />
          </Stack>
          <Stack direction="row" gap={3} flexWrap="wrap">
            <Fact
              label="Mag V"
              value={dso?.mag_v != null ? dso.mag_v.toFixed(1) : "—"}
            />
            <Fact
              label="Mag B"
              value={dso?.mag_b != null ? dso.mag_b.toFixed(1) : "—"}
            />
          </Stack>
        </Stack>

        {/* External-reference chip now lives in the header next to the
            designation pills. */}

        {/* ── Score Breakdown (collapsed by default, pill always visible) ── */}
        {(previewScoreQuery.data ?? target) && (() => {
          const scoreItem = previewScoreQuery.data ?? target!;
          return (
            <Box sx={{ mt: 2 }}>
              <Stack direction="row" alignItems="center" gap={0.5} sx={{ cursor: "pointer" }} onClick={() => setScoreOpen((v) => !v)}>
                <IconButton size="small" sx={{ p: 0.25 }}>
                  {scoreOpen ? <ExpandLessIcon sx={{ fontSize: 18 }} /> : <ExpandMoreIcon sx={{ fontSize: 18 }} />}
                </IconButton>
                <Typography variant="subtitle2" fontWeight={600}>Score</Typography>
                <ScoreChip
                  scorePct={scoreItem.score_pct}
                  qualityLabel={scoreItem.quality_label}
                  gateFailures={scoreItem.score_breakdown?.gate_failures}
                  size="small"
                />
              </Stack>
              <Collapse in={scoreOpen}>
                <ScoreBreakdownSection item={scoreItem} />
              </Collapse>
            </Box>
          );
        })()}

        {/* ── Sky Position (collapsible) ── */}
        <Box sx={{ mt: 2 }}>
          <Stack direction="row" alignItems="center" gap={0.5} sx={{ cursor: "pointer" }} onClick={() => setSkyPosOpen((v) => !v)}>
            <IconButton size="small" sx={{ p: 0.25 }}>
              {skyPosOpen ? <ExpandLessIcon sx={{ fontSize: 18 }} /> : <ExpandMoreIcon sx={{ fontSize: 18 }} />}
            </IconButton>
            <Typography variant="subtitle2" fontWeight={600}>Sky position</Typography>
          </Stack>
          <Collapse in={skyPosOpen}>
            {previewLocationId == null ? (
              <Box sx={{ p: 4, textAlign: "center" }}>
                <Typography variant="body2" color="text.secondary">
                  Pick a location in the header above to see this object's sky track.
                </Typography>
              </Box>
            ) : skyTrackQuery.isLoading ? (
              <Box sx={{ p: 4, display: "flex", justifyContent: "center" }}>
                <CircularProgress size={24} />
              </Box>
            ) : skyTrackQuery.data ? (
              <SkyPositionView track={skyTrackQuery.data} tz={tz} />
            ) : null}
          </Collapse>
        </Box>

        {/* ── Best Time of Year (collapsible, with moon filter) ── */}
        {previewLocationId != null && (
          <Box sx={{ mt: 2 }}>
            <Stack direction="row" alignItems="center" gap={0.5} sx={{ cursor: "pointer" }} onClick={() => setBestTimeOpen((v) => !v)}>
              <IconButton size="small" sx={{ p: 0.25 }}>
                {bestTimeOpen ? <ExpandLessIcon sx={{ fontSize: 18 }} /> : <ExpandMoreIcon sx={{ fontSize: 18 }} />}
              </IconButton>
              <Typography variant="subtitle2" fontWeight={600}>Best time of year</Typography>
            </Stack>
            <Collapse in={bestTimeOpen}>
              <Typography variant="caption" color="text.secondary">
                Hours above{" "}
                {effectiveHorizon?.type === "artificial" &&
                effectiveHorizon.flat_altitude_deg != null
                  ? `${effectiveHorizon.flat_altitude_deg.toFixed(0)}°`
                  : effectiveHorizon?.name ?? "horizon"}{" "}
                during astronomical darkness, by night.
              </Typography>

              <MoonFilterControls
                enabled={moonFilterEnabled}
                onEnabledChange={setMoonFilterEnabled}
                maxIllumination={maxIllumination}
                onMaxIlluminationChange={setMaxIllumination}
                minSeparation={minSeparation}
                onMinSeparationChange={setMinSeparation}
                moonCombine={moonCombine}
                onMoonCombineChange={setMoonCombine}
              />

              <Box sx={{ mt: 1, position: "relative", minHeight: 346 }}>
                {annualHoursQuery.data && (
                  <BestTimeOfYearChart track={annualHoursQuery.data} height={346} />
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
                      borderRadius: 1,
                      pointerEvents: "none",
                    }}
                  >
                    <CircularProgress size={28} />
                  </Box>
                )}
              </Box>
            </Collapse>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}
