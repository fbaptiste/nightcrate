import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import FormControlLabel from "@mui/material/FormControlLabel";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { convertRaDecAltAz, type RaDecAltAzResponse } from "@/api/calculators";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import { useCalculatorLocation } from "@/components/calculators/CalculatorLocationBar";
import { useDebounce } from "@/lib/useDebounce";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";

type Direction = "forward" | "reverse";

/** Format a Date as the local `YYYY-MM-DDTHH:mm` value expected by
 *  `<input type="datetime-local">`. */
function toLocalDateTimeInput(d: Date): string {
  const pad = (n: number) => (n < 10 ? `0${n}` : String(n));
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

/**
 * RA/Dec ↔ Alt/Az converter. Location-aware — the selected location is used
 * as the EarthLocation for the AltAz transform.
 */
export default function RaDecAltAzCalc() {
  const { locationId } = useCalculatorLocation();
  const [direction, setDirection] = useState<Direction>("forward");
  const [useNow, setUseNow] = useState(true);
  const [manualTime, setManualTime] = useState(() =>
    toLocalDateTimeInput(new Date()),
  );

  // Forward inputs
  const [raDeg, setRaDeg] = useState("");
  const [decDeg, setDecDeg] = useState("");
  // Reverse inputs
  const [altDeg, setAltDeg] = useState("");
  const [azDeg, setAzDeg] = useState("");

  const debouncedRa = useDebounce(raDeg, 200);
  const debouncedDec = useDebounce(decDeg, 200);
  const debouncedAlt = useDebounce(altDeg, 200);
  const debouncedAz = useDebounce(azDeg, 200);
  const debouncedManual = useDebounce(manualTime, 200);

  const [result, setResult] = useState<RaDecAltAzResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Validate inputs up front so we skip round trips when nothing valid.
  const inputValid = useMemo(() => {
    if (direction === "forward") {
      const ra = parseFloat(debouncedRa);
      const dec = parseFloat(debouncedDec);
      if (isNaN(ra) || ra < 0 || ra > 360) return false;
      if (isNaN(dec) || dec < -90 || dec > 90) return false;
      return true;
    }
    const alt = parseFloat(debouncedAlt);
    const az = parseFloat(debouncedAz);
    if (isNaN(alt) || alt < 0 || alt > 90) return false;
    if (isNaN(az) || az < 0 || az > 360) return false;
    return true;
  }, [direction, debouncedRa, debouncedDec, debouncedAlt, debouncedAz]);

  useEffect(() => {
    if (locationId == null) return;
    if (!inputValid) {
      setResult(null);
      setError(null);
      return;
    }

    let cancelled = false;
    const timestampIso = useNow
      ? null
      : // Convert the local-datetime input to an ISO string (includes tz offset)
        new Date(debouncedManual).toISOString();

    const body =
      direction === "forward"
        ? {
            direction,
            ra_deg: parseFloat(debouncedRa),
            dec_deg: parseFloat(debouncedDec),
            timestamp_iso: timestampIso,
            location_id: locationId,
          }
        : {
            direction,
            alt_deg: parseFloat(debouncedAlt),
            az_deg: parseFloat(debouncedAz),
            timestamp_iso: timestampIso,
            location_id: locationId,
          };

    convertRaDecAltAz(body)
      .then((r) => {
        if (cancelled) return;
        setResult(r);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setResult(null);
        setError(err instanceof Error ? err.message : "Conversion failed");
      });
    return () => {
      cancelled = true;
    };
  }, [
    locationId,
    direction,
    useNow,
    inputValid,
    debouncedRa,
    debouncedDec,
    debouncedAlt,
    debouncedAz,
    debouncedManual,
  ]);

  if (locationId == null) {
    return (
      <Typography color="text.secondary">
        Select a location above to run RA/Dec ↔ Alt/Az conversions.
      </Typography>
    );
  }

  return (
    <Stack spacing={3}>
      <Typography variant="h5">RA/Dec &#8596; Alt/Az</Typography>

      {/* Direction toggle + time controls */}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={2}
          alignItems={{ xs: "stretch", md: "center" }}
        >
          <ToggleButtonGroup
            value={direction}
            exclusive
            onChange={(_e, v: Direction | null) => v && setDirection(v)}
            size="small"
          >
            <ToggleButton value="forward">RA/Dec &rarr; Alt/Az</ToggleButton>
            <ToggleButton value="reverse">Alt/Az &rarr; RA/Dec</ToggleButton>
          </ToggleButtonGroup>

          <FormControlLabel
            control={
              <Checkbox
                checked={useNow}
                onChange={(e) => setUseNow(e.target.checked)}
                size="small"
              />
            }
            label="Use current time"
          />

          <TextField
            label="Observation time (local)"
            type="datetime-local"
            size="small"
            value={manualTime}
            onChange={(e) => setManualTime(e.target.value)}
            disabled={useNow}
            slotProps={{ inputLabel: { shrink: true } }}
            sx={{ minWidth: 220 }}
          />
        </Stack>
      </Paper>

      <Grid container spacing={3}>
        {/* Inputs */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2.5, height: "100%" }}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
              Input
            </Typography>
            {direction === "forward" ? (
              <Stack spacing={2}>
                <TextField
                  label="RA (degrees)"
                  type="number"
                  value={raDeg}
                  onChange={(e) => setRaDeg(e.target.value)}
                  helperText="0 to 360"
                  slotProps={{ htmlInput: { step: "any", min: 0, max: 360 } }}
                  size="small"
                  fullWidth
                />
                <TextField
                  label="Dec (degrees)"
                  type="number"
                  value={decDeg}
                  onChange={(e) => setDecDeg(e.target.value)}
                  helperText="-90 to 90"
                  slotProps={{ htmlInput: { step: "any", min: -90, max: 90 } }}
                  size="small"
                  fullWidth
                />
              </Stack>
            ) : (
              <Stack spacing={2}>
                <TextField
                  label="Altitude (degrees)"
                  type="number"
                  value={altDeg}
                  onChange={(e) => setAltDeg(e.target.value)}
                  helperText="0 (horizon) to 90 (zenith)"
                  slotProps={{ htmlInput: { step: "any", min: 0, max: 90 } }}
                  size="small"
                  fullWidth
                />
                <TextField
                  label="Azimuth (degrees)"
                  type="number"
                  value={azDeg}
                  onChange={(e) => setAzDeg(e.target.value)}
                  helperText="0 = N, 90 = E, 180 = S, 270 = W"
                  slotProps={{ htmlInput: { step: "any", min: 0, max: 360 } }}
                  size="small"
                  fullWidth
                />
              </Stack>
            )}
            {error && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                {error}
              </Alert>
            )}
          </Paper>
        </Grid>

        {/* Outputs */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2.5, height: "100%" }}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
              Result
            </Typography>
            {result ? (
              <Stack spacing={1.25}>
                <OutputRow
                  label="RA"
                  value={`${result.ra_deg.toFixed(4)}\u00B0`}
                />
                <OutputRow
                  label="Dec"
                  value={`${result.dec_deg.toFixed(4)}\u00B0`}
                />
                <OutputRow
                  label="Altitude"
                  value={`${result.alt_deg.toFixed(4)}\u00B0`}
                />
                <OutputRow
                  label="Azimuth"
                  value={`${result.az_deg.toFixed(4)}\u00B0`}
                />
                <OutputRow
                  label="Airmass"
                  value={
                    result.airmass != null ? result.airmass.toFixed(2) : "—"
                  }
                />
                <Box sx={{ pt: 1 }}>
                  <Chip
                    label={
                      result.below_horizon ? "Below horizon" : "Above horizon"
                    }
                    size="small"
                    sx={{
                      bgcolor: result.below_horizon ? RIG_ORANGE : RIG_BLUE,
                      color: "#ffffff",
                      fontWeight: 600,
                    }}
                  />
                </Box>
              </Stack>
            ) : (
              <Typography color="text.secondary" variant="body2">
                Enter values to see the converted coordinates.
              </Typography>
            )}
          </Paper>
        </Grid>
      </Grid>

      <CalculatorAboutSection>
        <p>
          Uses <code>astropy</code> to transform between the{" "}
          <strong>ICRS</strong> (equatorial) frame and the <strong>AltAz</strong>{" "}
          frame of the selected location&rsquo;s <code>EarthLocation</code>.
        </p>
        <p>
          <strong>Airmass:</strong> Kasten &amp; Young (1989) secant
          approximation; <code>null</code> when the target is below the horizon.
        </p>
        <p>
          Azimuth convention: 0&deg; = north, increasing eastward (0 &rarr; 90
          = N &rarr; E).
        </p>
      </CalculatorAboutSection>
    </Stack>
  );
}

function OutputRow({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: "flex", alignItems: "baseline", gap: 1 }}>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ minWidth: 90 }}
      >
        {label}
      </Typography>
      <Typography variant="h6" sx={{ fontFamily: "monospace" }}>
        {value}
      </Typography>
    </Box>
  );
}
