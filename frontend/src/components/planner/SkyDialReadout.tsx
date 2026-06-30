/**
 * Shared text readout for the planner sky-position dials (flat + 3-D dome).
 * Both renderings show the same Target / Moon / Separation / Illumination
 * block so they read identically when compared side by side.
 *
 * The dial encodes bearing + height, NOT true angular separation (two points
 * can share a bearing yet be far apart), so the numeric separation is always
 * shown here.
 */
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";
import { azLabel } from "./skyDial";
import type { SkyDialSample } from "./skyDial";

export default function SkyDialReadout({
  targetAz,
  targetAlt,
  moonAz,
  moonAlt,
  moonIllumPct,
  separationDeg,
}: SkyDialSample) {
  return (
    <Typography variant="body2" component="div" sx={{ lineHeight: 1.9 }}>
      <Box component="span" sx={{ color: RIG_BLUE, fontWeight: 600 }}>
        Target
      </Box>{" "}
      {azLabel(targetAz)} · {Math.round(targetAlt)}° alt
      {targetAlt <= 0 && " (below horizon)"}
      <br />
      <Box component="span" sx={{ color: RIG_ORANGE, fontWeight: 600 }}>
        Moon
      </Box>{" "}
      {azLabel(moonAz)} · {Math.round(moonAlt)}° alt
      {moonAlt <= 0 && " (below horizon)"}
      <br />
      <Box component="span" sx={{ color: "text.secondary" }}>
        Separation {Math.round(separationDeg)}°
      </Box>
      <br />
      <Box component="span" sx={{ color: "text.secondary" }}>
        Illumination {Math.round(moonIllumPct)}%
      </Box>
    </Typography>
  );
}
