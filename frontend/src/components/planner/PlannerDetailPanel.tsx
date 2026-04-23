/**
 * Planner detail panel — larger thumbnail + sky-position graph + metadata.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import {
  fetchAnnualHours,
  fetchSkyTrack,
  type PlannerTargetItem,
} from "@/api/planner";
import { fetchDso } from "@/api/dsos";
import { fetchHorizons, type Horizon } from "@/api/horizons";
import { type Rig } from "@/api/rigs";
import { type Location } from "@/api/locations";
import { useSettingsStore } from "@/stores/settingsStore";
import { displayConstellation } from "@/lib/constellations";
import { formatDistance } from "@/lib/distanceFormat";
import { displayDsoType, dsoTypeColor } from "@/lib/dsoTypeNames";
import SkyPreview from "@/components/dso/SkyPreview";
import BestTimeOfYearChart from "./BestTimeOfYearChart";
import SkyPositionGraph from "./SkyPositionGraph";
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

function coverageNarrative(pct: number): string {
  if (pct < 5) return `fills only ~${pct.toFixed(0)}% of the frame — lost in the field`;
  if (pct < 15) return `covers ${pct.toFixed(0)}% of the frame — tight crop recommended`;
  if (pct < 50) return `fits comfortably at ${pct.toFixed(0)}%`;
  if (pct <= 90) return `fills the frame nicely at ${pct.toFixed(0)}%`;
  if (pct < 150) return `covers ${pct.toFixed(0)}% of the frame — will be cropped`;
  return `far larger than the frame (${pct.toFixed(0)}%) — mosaic needed`;
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

  // "Best time of year" controls — moon-separation dropdown only now
  // (horizon threshold comes from the dedicated horizon selector).
  // ``moonSepDeg`` is the minimum moon–target separation the night
  // needs to count; ``0`` means "ignore moon". Default sourced from
  // the user's ``planner_moon_sep_deg`` setting so power users who
  // always shoot LRGB can land on e.g. 60° without reconfiguring the
  // dropdown per target.
  const settings = useSettingsStore((s) => s.settings);
  const moonSepDefault = settings?.planner_moon_sep_deg ?? 0;
  const [moonSepDeg, setMoonSepDeg] = useState<number>(moonSepDefault);

  useEffect(() => {
    if (dsoId != null) {
      setMoonSepDeg(moonSepDefault);
    }
    // Re-running on ``moonSepDefault`` would snap the slider back to
    // the setting whenever Settings is edited — only reset on DSO
    // open / change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dsoId]);

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
      moonSepDeg,
    ],
    queryFn: () =>
      fetchAnnualHours(dsoId as number, previewLocationId as number, {
        horizonId: effectiveHorizon?.id,
        moonSepDeg,
      }),
    enabled:
      dsoId != null && previewLocationId != null && effectiveHorizon != null,
    staleTime: 60 * 60 * 1000,
  });

  const open = dsoId != null;
  const dso = dsoQuery.data;

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
  const rigName = previewRig?.name ?? null;

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
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle sx={{ display: "flex", alignItems: "flex-start", gap: 2, py: 1.25 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" gap={1.5} alignItems="baseline" flexWrap="wrap">
            <Typography variant="h6">{dso?.primary_designation ?? "…"}</Typography>
            {dso?.constellation && (
              <Typography variant="body2" color="text.secondary">
                {displayConstellation(dso.constellation)}
              </Typography>
            )}
          </Stack>
          {dso?.common_name && (
            <Typography variant="body2" color="text.secondary">
              {dso.common_name}
            </Typography>
          )}
          {/* Type + distance chips — the two facts most users want at a
              glance. Type uses the friendly ``displayDsoType`` form
              (e.g. "Emission Nebula" not "EmN"); distance shows both
              parsecs and light-years so beginners have an intuitive
              second unit. Placed right under the common-name (or
              designation when no common name) so the header reads
              name-first, facts-second. */}
          {(dso?.obj_type || distance) && (
            <Stack direction="row" gap={0.75} flexWrap="wrap" sx={{ mt: 0.75 }}>
              {dso?.obj_type && (
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
              {distance && (
                <Chip
                  label={`${distance.primary} · ${distance.secondary}`}
                  size="small"
                  variant="outlined"
                />
              )}
            </Stack>
          )}
          {/* Designation pills — primary filled, alternates outlined.
              Kept pure-chip so the visual language is "identifiers"
              across the row; interactive external references render
              as a separate link-styled line below so the user can
              tell what's clickable without relying on a hover state. */}
          {dso && dso.designations.length > 0 && (
            <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 0.75 }}>
              {dso.designations.map((d) => (
                <Chip
                  key={`${d.catalog}-${d.identifier}`}
                  label={d.display_form}
                  size="small"
                  variant={d.is_primary ? "filled" : "outlined"}
                  color={d.is_primary ? "primary" : "default"}
                />
              ))}
            </Stack>
          )}

          {/* Wikipedia link(s) — theme primary colour + underline +
              open-in-new icon. Deliberately NOT a chip: when sitting
              next to non-clickable designation chips, chip styling
              made the external link look indistinguishable from the
              cross-references. The link shape makes the "opens in a
              new tab" affordance explicit. ``stopPropagation`` keeps
              clicks from bubbling to any future ancestor handler. */}
          {dso &&
            dso.external_refs.some((ref) => ref.provider === "wikipedia") && (
              <Stack
                direction="row"
                gap={1.5}
                flexWrap="wrap"
                alignItems="center"
                sx={{ mt: 0.75 }}
              >
                {dso.external_refs
                  .filter((ref) => ref.provider === "wikipedia")
                  .map((ref) => (
                    <Link
                      key={`wikipedia-${ref.identifier}`}
                      href={ref.url ?? undefined}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      underline="hover"
                      aria-label={`Open Wikipedia article: ${
                        ref.label ?? ref.identifier
                      } (opens in new tab)`}
                      sx={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 0.5,
                        fontSize: "0.85rem",
                        fontWeight: 500,
                      }}
                    >
                      Wikipedia: {ref.label ?? ref.identifier}
                      <OpenInNewIcon sx={{ fontSize: 14 }} />
                    </Link>
                  ))}
              </Stack>
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

        {/* Compact fact grid — one line per fact; auto-fit packs as many
            columns as the dialog width allows. */}
        <Box
          sx={{
            mt: 1.5,
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
            columnGap: 2,
            rowGap: 0.25,
          }}
        >
          <Fact
            label="Mag V"
            value={dso?.mag_v != null ? dso.mag_v.toFixed(1) : "—"}
          />
          <Fact
            label="Mag B"
            value={dso?.mag_b != null ? dso.mag_b.toFixed(1) : "—"}
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
            label="Hours visible"
            value={
              target?.hours_visible != null
                ? `${target.hours_visible.toFixed(1)} h`
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
              target?.max_altitude_deg != null && target.peak_time_utc != null
                ? `${target.max_altitude_deg.toFixed(0)}° @ ${formatLocalTime(
                    target.peak_time_utc,
                    tz,
                  )}`
                : "—"
            }
          />
          <Fact
            label="Meridian"
            value={
              target?.altitude_at_transit_deg != null &&
              target.transit_time_utc != null
                ? `${target.altitude_at_transit_deg.toFixed(0)}° @ ${formatLocalTime(
                    target.transit_time_utc,
                    tz,
                  )}`
                : "—"
            }
          />
          <Fact
            label="Moon separation"
            value={
              target?.min_moon_separation_deg != null
                ? `${target.min_moon_separation_deg.toFixed(0)}°`
                : "—"
            }
          />
          {rigFov && (
            <Fact
              label="FOV coverage"
              value={
                coveragePct != null ? `${coveragePct.toFixed(0)}%` : "—"
              }
            />
          )}
        </Box>

        {coveragePct != null && rigName && (
          <Typography variant="body2" sx={{ mt: 1.5 }}>
            This object {coverageNarrative(coveragePct)} in your <strong>{rigName}</strong> rig.
          </Typography>
        )}

        {/* External-reference chip now lives in the header next to the
            designation pills. */}

        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2" fontWeight={600}>
            Sky position
          </Typography>
          {previewLocationId == null ? (
            // Anytime mode (or any other state where the panel has
            // no location). The sky-track computation needs a
            // location; surface a friendly prompt rather than a
            // spinner that never resolves.
            <Box sx={{ p: 4, textAlign: "center" }}>
              <Typography variant="body2" color="text.secondary">
                Pick a location in the header above to see this
                object's sky track.
              </Typography>
            </Box>
          ) : skyTrackQuery.isLoading ? (
            <Box sx={{ p: 4, display: "flex", justifyContent: "center" }}>
              <CircularProgress size={24} />
            </Box>
          ) : skyTrackQuery.data ? (
            <SkyPositionGraph track={skyTrackQuery.data} tz={tz} />
          ) : null}
        </Box>

        {skyTrackQuery.data && (
          <Stack direction="row" gap={3} sx={{ mt: 2 }} flexWrap="wrap">
            <Typography variant="caption" color="text.secondary">
              Astro dark: {formatLocalTime(skyTrackQuery.data.twilight.astro_start_utc, tz)} –{" "}
              {formatLocalTime(skyTrackQuery.data.twilight.astro_end_utc, tz)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Moon phase: {Math.round(skyTrackQuery.data.moon_phase_pct)}%
            </Typography>
          </Stack>
        )}

        {/* "Best time of year" chart — hours per night above the
            selected horizon during astro dark, optionally with moon
            avoidance. Hidden entirely when no location is selected —
            the calculation is location-dependent. */}
        {previewLocationId != null && (
          <Box sx={{ mt: 3 }}>
            <Typography variant="subtitle2" fontWeight={600}>
              Best time of year
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Hours above{" "}
              {effectiveHorizon?.type === "artificial" &&
              effectiveHorizon.flat_altitude_deg != null
                ? `${effectiveHorizon.flat_altitude_deg.toFixed(0)}°`
                : effectiveHorizon?.name ?? "horizon"}{" "}
              during astronomical darkness, by night.
            </Typography>

            {/* Controls row — moon-separation dropdown. Horizon choice
                comes from the header selector above. */}
            <Stack
              direction="row"
              gap={2}
              alignItems="center"
              flexWrap="wrap"
              sx={{ mt: 1 }}
            >
              <Tooltip
                title={
                  "Minimum moon–target separation required for a sample to count. " +
                  "``Ignore moon`` (0°) matches narrowband behaviour — every hour above " +
                  "the horizon during astro dark is counted. Larger values filter out " +
                  "nights when the moon is close to the target, recommended for LRGB / " +
                  "broadband imaging."
                }
                arrow
                placement="top"
              >
                <FormControl size="small" variant="standard" sx={{ minWidth: 160 }}>
                  <Select
                    value={String(moonSepDeg)}
                    onChange={(e) => setMoonSepDeg(Number(e.target.value))}
                    sx={{ fontSize: "0.85rem" }}
                    inputProps={{ "aria-label": "Minimum moon separation" }}
                  >
                    <MenuItem value="0">Ignore moon</MenuItem>
                    {[15, 30, 45, 60, 75, 90].map((deg) => (
                      <MenuItem key={deg} value={String(deg)}>
                        Moon &gt; {deg}&deg;
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Tooltip>
            </Stack>

            {/* Fixed-height container so the panel body doesn't
                shrink when the chart swaps to the spinner. 200 px
                matches ``BestTimeOfYearChart``'s default height —
                keep them aligned if one changes. */}
            <Box sx={{ mt: 1, position: "relative", minHeight: 200 }}>
              {annualHoursQuery.data && (
                <BestTimeOfYearChart track={annualHoursQuery.data} />
              )}
              {annualHoursQuery.isFetching && (
                // Centred spinner while a new fetch is in flight —
                // overlay when we have prior data, full-area when
                // we don't.
                <Box
                  sx={{
                    position: "absolute",
                    inset: 0,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    bgcolor: annualHoursQuery.data
                      ? "rgba(0, 0, 0, 0.25)"
                      : "transparent",
                    borderRadius: 1,
                    pointerEvents: "none",
                  }}
                >
                  <CircularProgress size={28} />
                </Box>
              )}
            </Box>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}
