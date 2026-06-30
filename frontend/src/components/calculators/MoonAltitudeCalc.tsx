import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { fetchMoonYear } from "@/api/planner";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import { useCalculatorLocation } from "@/components/calculators/CalculatorLocationBar";
import MoonAltitudeChart from "@/components/calculators/MoonAltitudeChart";

/**
 * Moon Altitude (Year) — the Moon's peak altitude during astronomical darkness
 * across a year for the selected location, with illumination and new/full-moon
 * markers. Location comes from the shared CalculatorLocationBar.
 */
export default function MoonAltitudeCalc() {
  const { locationId } = useCalculatorLocation();
  const [year, setYear] = useState(() => new Date().getFullYear());

  // Deep-link from "Tonight at a Glance": ``?year=YYYY`` pre-selects the
  // year, then the param is cleared so a manual ±year step or a reload
  // doesn't snap back. Location arrives via the shared calculators store,
  // so only the year needs threading. Read-then-clear pattern mirrors the
  // equipment list's ``?select=`` handling.
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    const yearParam = searchParams.get("year");
    if (yearParam == null) return;
    const parsed = Number.parseInt(yearParam, 10);
    if (Number.isFinite(parsed) && parsed >= 1900 && parsed <= 3000) {
      setYear(parsed);
    }
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams]);

  const query = useQuery({
    queryKey: ["moon-year", locationId, year],
    queryFn: () => fetchMoonYear(locationId!, year),
    enabled: locationId != null,
    staleTime: 5 * 60_000,
  });

  if (locationId == null) {
    return (
      <Typography color="text.secondary">
        Select a location above to plot the Moon&rsquo;s altitude over the year.
      </Typography>
    );
  }

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h5">Moon Altitude (Year)</Typography>
        <Typography variant="body2" color="text.secondary">
          The Moon&rsquo;s peak altitude during astronomical darkness each night —
          new moons (teal) are your dark-sky imaging windows, full moons (orange)
          the bright nights to avoid.
        </Typography>
      </Box>

      <Stack direction="row" spacing={1} alignItems="center">
        <IconButton size="small" onClick={() => setYear((y) => y - 1)}>
          <ChevronLeftIcon />
        </IconButton>
        <Typography variant="h6" sx={{ minWidth: 64, textAlign: "center" }}>
          {year}
        </Typography>
        <IconButton size="small" onClick={() => setYear((y) => y + 1)}>
          <ChevronRightIcon />
        </IconButton>
      </Stack>

      <Paper variant="outlined" sx={{ p: 2 }}>
        {query.isLoading ? (
          <Typography color="text.secondary" sx={{ py: 6, textAlign: "center" }}>
            Computing the year&rsquo;s Moon track…
          </Typography>
        ) : query.isError ? (
          <Typography color="error" sx={{ py: 6, textAlign: "center" }}>
            Could not compute the Moon track for this location.
          </Typography>
        ) : query.data ? (
          <MoonAltitudeChart data={query.data} />
        ) : null}
      </Paper>

      <CalculatorAboutSection>
        <p>
          For each night, this plots the highest altitude the Moon reaches{" "}
          <strong>while the sky is astronomically dark</strong> (Sun below
          &minus;18&deg;) at the selected location, plus the Moon&rsquo;s
          illuminated fraction. Computed with <code>astropy</code> on a 5-minute
          grid across the year.
        </p>
        <p>
          The shape is seasonal: in winter the long dark window catches the
          Moon&rsquo;s transit, giving one clean hump per month; in summer the
          short window and the low summer full Moon split it into twin humps.
        </p>
        <p>
          <strong>New-moon</strong> markers (filled teal, with guide lines) mark
          the darkest nights for deep-sky imaging; <strong>full-moon</strong>{" "}
          markers (orange rings) the brightest. Hover snaps to the nearest phase.
          Phase dates are day-precise.
        </p>
      </CalculatorAboutSection>
    </Stack>
  );
}
