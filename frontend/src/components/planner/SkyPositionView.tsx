/**
 * Sky-position section of the planner detail panel: the alt-az sky-dome
 * dial paired with the existing altitude-vs-time chart. Owns the shared
 * time cursor — hovering/scrubbing the chart drives the dial; on leave
 * the dial falls back to a sensible default sample ("now" if the night
 * is in progress, else the object's peak/transit).
 */
import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import type { SkyTrackResponse } from "@/api/planner";
import SkyPositionGraph from "./SkyPositionGraph";
import SkyDomeChart from "./SkyDomeChart";
import SkyDome3DChart from "./SkyDome3DChart";

interface Props {
  track: SkyTrackResponse;
  tz: string;
}

type DomeStyle = "3d" | "flat";

/** Index of the sample nearest a given instant, or null when the instant
 *  falls outside the track window. */
function nearestIndex(times: number[], targetMs: number): number | null {
  if (times.length === 0) return null;
  if (targetMs < times[0] || targetMs > times[times.length - 1]) return null;
  let best = 0;
  let bestDist = Infinity;
  for (let i = 0; i < times.length; i++) {
    const d = Math.abs(times[i] - targetMs);
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  }
  return best;
}

const DOME_STYLE_KEY = "nightcrate.skyDomeStyle";

function readDomeStyle(): DomeStyle {
  try {
    const v = localStorage.getItem(DOME_STYLE_KEY);
    if (v === "3d" || v === "flat") return v;
  } catch {
    /* localStorage may be unavailable (private mode); fall through */
  }
  return "flat";
}

export default function SkyPositionView({ track, tz }: Props) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  // Persisted across sessions; defaults to Flat, retains the user's choice.
  const [domeStyle, setDomeStyle] = useState<DomeStyle>(readDomeStyle);

  const changeDomeStyle = (v: DomeStyle | null) => {
    if (!v) return;
    setDomeStyle(v);
    try {
      localStorage.setItem(DOME_STYLE_KEY, v);
    } catch {
      /* ignore persistence failure */
    }
  };

  const timesMs = useMemo(
    () => track.times_utc.map((t) => new Date(t).getTime()),
    [track.times_utc],
  );

  // Default sample shown when the user isn't scrubbing: the current
  // moment if tonight's window is in progress, otherwise the peak/transit
  // (the moment the planning eye cares about most).
  const defaultIdx = useMemo(() => {
    const nowIdx = nearestIndex(timesMs, Date.now());
    if (nowIdx != null) return nowIdx;
    const peakIdx = nearestIndex(timesMs, new Date(track.peak_time_utc).getTime());
    if (peakIdx != null) return peakIdx;
    // Peak falls outside the window — fall back to the highest sample.
    let best = 0;
    for (let i = 1; i < track.object_altitude_deg.length; i++) {
      if (track.object_altitude_deg[i] > track.object_altitude_deg[best]) best = i;
    }
    return best;
  }, [timesMs, track.peak_time_utc, track.object_altitude_deg]);

  const idx = hoverIdx ?? defaultIdx;
  const sample = {
    targetAz: track.object_azimuth_deg[idx],
    targetAlt: track.object_altitude_deg[idx],
    moonAz: track.moon_azimuth_deg[idx],
    moonAlt: track.moon_altitude_deg[idx],
    moonIllumPct: track.moon_phase_pct,
    separationDeg: track.moon_separation_deg[idx],
  };

  // Full-night paths across the sky for the dome to draw.
  const targetPath = useMemo(
    () =>
      track.object_azimuth_deg.map((az, i) => ({
        az,
        alt: track.object_altitude_deg[i],
      })),
    [track.object_azimuth_deg, track.object_altitude_deg],
  );
  const moonPath = useMemo(
    () =>
      track.moon_azimuth_deg.map((az, i) => ({ az, alt: track.moon_altitude_deg[i] })),
    [track.moon_azimuth_deg, track.moon_altitude_deg],
  );

  return (
    <Box>
      <Stack direction="row" justifyContent="center" sx={{ mt: 1 }}>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={domeStyle}
          onChange={(_, v: DomeStyle | null) => changeDomeStyle(v)}
        >
          <ToggleButton value="flat">Flat</ToggleButton>
          <ToggleButton value="3d">3D dome</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      <Box sx={{ mt: 1 }}>
        {domeStyle === "3d" ? (
          <SkyDome3DChart {...sample} targetPath={targetPath} moonPath={moonPath} size={300} />
        ) : (
          <SkyDomeChart {...sample} targetPath={targetPath} moonPath={moonPath} size={300} />
        )}
      </Box>
      <SkyPositionGraph track={track} tz={tz} onActiveIndexChange={setHoverIdx} />
    </Box>
  );
}
