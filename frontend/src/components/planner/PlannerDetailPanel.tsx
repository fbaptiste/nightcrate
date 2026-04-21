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
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import { fetchSkyTrack, type PlannerTargetItem } from "@/api/planner";
import { fetchDso } from "@/api/dsos";
import { type Rig } from "@/api/rigs";
import { type Location } from "@/api/locations";
import { displayConstellation } from "@/lib/constellations";
import { formatDistance } from "@/lib/distanceFormat";
import SkyPreview from "@/components/dso/SkyPreview";
import SkyPositionGraph from "./SkyPositionGraph";
import FovSimulator from "./FovSimulator";

interface Props {
  dsoId: number | null;
  target: PlannerTargetItem | null;
  /** Location the parent page has selected — the preview dropdown
   *  starts from this value. Panel-local overrides NEVER propagate
   *  back to the parent (grid stays on the parent's choice). */
  selectedLocationId: number | null;
  locations: Location[];
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

function formatLocal(iso: string | null, tz: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: tz,
    });
  } catch {
    return "—";
  }
}

// Small helper — renders one `Label · Value` pair in the metadata grid
// as a single inline row so the fact list stays compact vertically.
function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Typography variant="body2" sx={{ lineHeight: 1.5 }}>
      <Box
        component="span"
        sx={{
          color: "text.secondary",
          textTransform: "uppercase",
          letterSpacing: 0.4,
          fontSize: "0.65rem",
          mr: 1,
        }}
      >
        {label}
      </Box>
      {value}
    </Typography>
  );
}

export default function PlannerDetailPanel({
  dsoId,
  target,
  selectedLocationId,
  locations,
  selectedRigId,
  rigs,
  onSelectDso,
  onClose,
}: Props) {
  // Local preview overrides — distinct from the parent's ``selectedLocationId``
  // and ``selectedRigId``. Changing either only affects what the panel
  // renders (sky track + simulator + fact grid + coverage narrative).
  // Each resets back to the parent's choice on target open.
  const [previewLocationId, setPreviewLocationId] = useState<number | null>(
    selectedLocationId,
  );
  const [previewRigId, setPreviewRigId] = useState<number | null>(selectedRigId);
  useEffect(() => {
    if (dsoId != null) {
      setPreviewLocationId(selectedLocationId);
      setPreviewRigId(selectedRigId);
    }
  }, [dsoId, selectedLocationId, selectedRigId]);

  const previewLocation = locations.find((l) => l.id === previewLocationId) ?? null;
  const tz = previewLocation?.timezone ?? "UTC";

  const dsoQuery = useQuery({
    queryKey: ["dso", dsoId],
    queryFn: () => fetchDso(dsoId as number),
    enabled: dsoId != null,
  });

  const skyTrackQuery = useQuery({
    queryKey: ["sky-track", dsoId, previewLocationId],
    queryFn: () => fetchSkyTrack(dsoId as number, previewLocationId as number),
    enabled: dsoId != null && previewLocationId != null,
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

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 2, py: 1.25 }}>
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
                from
              </Typography>
              <FormControl size="small" variant="standard" sx={{ minWidth: 140 }}>
                <Select
                  value={previewLocationId ?? ""}
                  onChange={(e) => {
                    const v = String(e.target.value);
                    setPreviewLocationId(v === "" ? null : Number(v));
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
          {rigs.length > 0 && (
            <Stack direction="row" gap={0.75} alignItems="center">
              <Typography variant="caption" color="text.secondary">
                with
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

        {/* Inline chip row — quick glance context. */}
        <Stack direction="row" gap={1} flexWrap="wrap" sx={{ mt: 1.5 }}>
          {dso?.obj_type && <Chip label={dso.obj_type} size="small" />}
          {dso?.distance_pc != null && (
            <Chip
              label={formatDistance(dso.distance_pc)?.primary ?? ""}
              size="small"
              variant="outlined"
            />
          )}
        </Stack>

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
            label="Max altitude"
            value={
              target?.max_altitude_deg != null && target.peak_time_utc != null
                ? `${target.max_altitude_deg.toFixed(0)}° @ ${formatLocal(
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
                ? `${target.altitude_at_transit_deg.toFixed(0)}° @ ${formatLocal(
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
              Astro dark: {formatLocal(skyTrackQuery.data.twilight.astro_start_utc, tz)} –{" "}
              {formatLocal(skyTrackQuery.data.twilight.astro_end_utc, tz)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Moon phase: {Math.round(skyTrackQuery.data.moon_phase_pct)}%
            </Typography>
          </Stack>
        )}
      </DialogContent>
    </Dialog>
  );
}
