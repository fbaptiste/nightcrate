import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router-dom";
import type { Night } from "@/api/weather";
import type { WeatherUnits } from "@/api/settings";
import { formatHours, formatNightDate, reasonLine, type ClockColumn } from "@/lib/weatherVerdict";
import HourStrip, { DarknessBand, HourAxis } from "./HourStrip";
import VerdictPill from "./VerdictPill";

export default function NightCard({
  night,
  clock,
  units,
  href,
  notCurrent = false,
  notCurrentLabel,
}: {
  night: Night;
  clock: ClockColumn[];
  units: WeatherUnits;
  href: string;
  notCurrent?: boolean;
  notCurrentLabel?: string;
}) {
  return (
    <Paper
      component={RouterLink}
      to={href}
      variant="outlined"
      sx={{
        p: 2,
        width: { xs: "100%", sm: 390 },
        minHeight: 168,
        display: "flex",
        flexDirection: "column",
        gap: 1,
        color: "inherit",
        textDecoration: "none",
        "&:hover": { borderColor: "primary.main", bgcolor: "action.hover" },
        "&:focus-visible": { outline: 2, outlineColor: "primary.main" },
      }}
    >
      <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
        <Typography variant="subtitle1" fontWeight={600}>Imaging verdict · {formatNightDate(night.date)}</Typography>
        <VerdictPill verdict={night.verdict} size="small" notCurrent={notCurrent} />
      </Box>
      {notCurrentLabel && (
        <Typography variant="caption" color="text.secondary">{notCurrentLabel}</Typography>
      )}
      <Typography variant="body2">{reasonLine(night, units)}</Typography>
      <Box sx={{ overflow: "hidden" }}>
        <HourAxis clock={clock} compact />
        <HourStrip night={night} clock={clock} height={32} compact />
        <Box sx={{ mt: "3px" }}><DarknessBand night={night} clock={clock} compact /></Box>
      </Box>
      <Typography variant="caption" color="text.secondary">
        {formatHours(night.clear_hours)} of {formatHours(night.dark_hours)} h usable
        {night.evaluated_from ? " remaining" : ""}
        {night.window_start && night.window_end ? ` · ${night.window_start}–${night.window_end}` : ""}
      </Typography>
    </Paper>
  );
}
