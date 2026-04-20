/**
 * Planner detail panel — larger thumbnail + sky-position graph + metadata.
 */
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import { fetchSkyTrack, type PlannerTargetItem } from "@/api/planner";
import { fetchDso } from "@/api/dsos";
import { displayConstellation } from "@/lib/constellations";
import { formatDistance } from "@/lib/distanceFormat";
import ThumbnailCell from "./ThumbnailCell";
import SkyPositionGraph from "./SkyPositionGraph";

interface Props {
  dsoId: number | null;
  target: PlannerTargetItem | null;
  locationId: number | null;
  locationName: string | null;
  rigFov: [number, number] | null;
  rigName: string | null;
  tz: string;
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

// Small helper — renders one `Label / Value` pair in the metadata grid.
function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Box>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ textTransform: "uppercase", letterSpacing: 0.5, fontSize: "0.65rem" }}
      >
        {label}
      </Typography>
      <Typography variant="body2" sx={{ mt: 0.25 }}>
        {value}
      </Typography>
    </Box>
  );
}

export default function PlannerDetailPanel({
  dsoId,
  target,
  locationId,
  locationName,
  rigFov,
  rigName,
  tz,
  onClose,
}: Props) {
  const dsoQuery = useQuery({
    queryKey: ["dso", dsoId],
    queryFn: () => fetchDso(dsoId as number),
    enabled: dsoId != null,
  });

  const skyTrackQuery = useQuery({
    queryKey: ["sky-track", dsoId, locationId],
    queryFn: () => fetchSkyTrack(dsoId as number, locationId as number),
    enabled: dsoId != null && locationId != null,
  });

  const open = dsoId != null;
  const dso = dsoQuery.data;

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
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 2 }}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6">{dso?.primary_designation ?? "…"}</Typography>
          {dso?.common_name && (
            <Typography variant="body2" color="text.secondary">
              {dso.common_name}
            </Typography>
          )}
        </Box>
        <IconButton size="small" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {/* Thumbnail: full-width, capped at the source image's native
            600 px so we never upscale. The backend sizes the FOV by
            the object's angular extent — it is NOT rig-aware. */}
        {dsoId != null && (
          <Box
            sx={{
              mx: "auto",
              maxWidth: 560,
              aspectRatio: "1 / 1",
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <ThumbnailCell dsoId={dsoId} size={560} variant="detail" />
          </Box>
        )}

        {/* Inline chip row — quick glance context. */}
        <Stack direction="row" gap={1} flexWrap="wrap" sx={{ mt: 2 }}>
          {dso?.obj_type && <Chip label={dso.obj_type} size="small" />}
          {dso?.constellation && (
            <Chip
              label={displayConstellation(dso.constellation)}
              size="small"
              variant="outlined"
            />
          )}
          {dso?.distance_pc != null && (
            <Chip
              label={formatDistance(dso.distance_pc)?.primary ?? ""}
              size="small"
              variant="outlined"
            />
          )}
        </Stack>

        {/* Structured fact grid — repeats everything visible in the list
            plus photographic magnitude and size from the DSO record. */}
        <Box
          sx={{
            mt: 2,
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
            columnGap: 3,
            rowGap: 1.5,
          }}
        >
          <Fact
            label="Visual magnitude"
            value={dso?.mag_v != null ? dso.mag_v.toFixed(1) : "—"}
          />
          <Fact
            label="Photographic magnitude"
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
            label="Constellation"
            value={displayConstellation(dso?.constellation ?? null) || "—"}
          />
          <Fact
            label="Hours visible"
            value={target != null ? `${target.hours_visible.toFixed(1)} h` : "—"}
          />
          <Fact
            label="Max altitude"
            value={
              target != null
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
              target?.altitude_at_transit_deg != null && target.transit_time_utc
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
          <Typography variant="body2" sx={{ mt: 2 }}>
            This object {coverageNarrative(coveragePct)} in your <strong>{rigName}</strong> rig.
          </Typography>
        )}

        <Box sx={{ mt: 3 }}>
          <Stack direction="row" gap={1} alignItems="baseline" justifyContent="space-between">
            <Typography variant="subtitle2" fontWeight={600}>
              Sky position
            </Typography>
            {locationName && (
              <Typography variant="caption" color="text.secondary">
                from {locationName}
              </Typography>
            )}
          </Stack>
          {skyTrackQuery.isLoading && (
            <Box sx={{ p: 4, display: "flex", justifyContent: "center" }}>
              <CircularProgress size={24} />
            </Box>
          )}
          {skyTrackQuery.data && (
            <SkyPositionGraph track={skyTrackQuery.data} tz={tz} />
          )}
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
