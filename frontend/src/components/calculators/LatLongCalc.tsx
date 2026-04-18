import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import {
  convertLatLongToDecimal,
  convertLatLongToSexagesimal,
  type LatLongToDecimalResponse,
  type LatLongToSexagesimalResponse,
} from "@/api/calculators";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import { useDebounce } from "@/lib/useDebounce";

/**
 * Two-panel lat/long converter:
 *  • Decimal → Sexagesimal (numeric TextFields → astropy-formatted string)
 *  • Sexagesimal → Decimal (free-form text → decimal degrees)
 */
export default function LatLongCalc() {
  // Panel A — decimal → sexagesimal
  const [latDec, setLatDec] = useState("");
  const [lonDec, setLonDec] = useState("");
  const debouncedLatDec = useDebounce(latDec, 200);
  const debouncedLonDec = useDebounce(lonDec, 200);
  const [sexResult, setSexResult] = useState<LatLongToSexagesimalResponse | null>(null);

  // Panel B — sexagesimal → decimal
  const [latSex, setLatSex] = useState("");
  const [lonSex, setLonSex] = useState("");
  const debouncedLatSex = useDebounce(latSex, 200);
  const debouncedLonSex = useDebounce(lonSex, 200);
  const [decResult, setDecResult] = useState<LatLongToDecimalResponse | null>(null);

  const [snack, setSnack] = useState<string | null>(null);

  // --- Client-side validation for the decimal inputs --------------------------
  const latDecNum = parseFloat(debouncedLatDec);
  const lonDecNum = parseFloat(debouncedLonDec);
  const latDecError =
    debouncedLatDec.trim() === ""
      ? null
      : isNaN(latDecNum) || latDecNum < -90 || latDecNum > 90
        ? "Latitude must be a number in [-90, 90]"
        : null;
  const lonDecError =
    debouncedLonDec.trim() === ""
      ? null
      : isNaN(lonDecNum) || lonDecNum < -180 || lonDecNum > 180
        ? "Longitude must be a number in [-180, 180]"
        : null;

  // Panel A: call backend only when both decimal fields parse cleanly.
  useEffect(() => {
    let cancelled = false;
    if (latDecError || lonDecError || isNaN(latDecNum) || isNaN(lonDecNum)) {
      setSexResult(null);
      return;
    }
    convertLatLongToSexagesimal(latDecNum, lonDecNum)
      .then((r) => {
        if (!cancelled) setSexResult(r);
      })
      .catch(() => {
        if (!cancelled) setSexResult(null);
      });
    return () => {
      cancelled = true;
    };
  }, [latDecNum, lonDecNum, latDecError, lonDecError]);

  // Panel B: backend handles per-field parsing + error reporting.
  useEffect(() => {
    let cancelled = false;
    const lat = debouncedLatSex.trim();
    const lon = debouncedLonSex.trim();
    if (!lat && !lon) {
      setDecResult(null);
      return;
    }
    convertLatLongToDecimal({
      latitude: lat || undefined,
      longitude: lon || undefined,
    })
      .then((r) => {
        if (!cancelled) setDecResult(r);
      })
      .catch(() => {
        if (!cancelled) setDecResult(null);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedLatSex, debouncedLonSex]);

  const copy = (value: string, label: string) => {
    navigator.clipboard
      .writeText(value)
      .then(() => setSnack(`${label} copied`))
      .catch(() => setSnack("Copy failed"));
  };

  return (
    <Stack spacing={3}>
      <Typography variant="h5">Lat / Long Converter</Typography>

      <Grid container spacing={3}>
        {/* Panel A — Decimal → Sexagesimal */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2.5, height: "100%" }}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
              Decimal → Sexagesimal
            </Typography>
            <Stack spacing={2}>
              <TextField
                label="Latitude"
                type="number"
                value={latDec}
                onChange={(e) => setLatDec(e.target.value)}
                error={Boolean(latDecError)}
                helperText={latDecError ?? "Decimal degrees, -90 to 90"}
                slotProps={{ htmlInput: { step: "any", min: -90, max: 90 } }}
                size="small"
                fullWidth
              />
              <TextField
                label="Longitude"
                type="number"
                value={lonDec}
                onChange={(e) => setLonDec(e.target.value)}
                error={Boolean(lonDecError)}
                helperText={lonDecError ?? "Decimal degrees, -180 to 180"}
                slotProps={{ htmlInput: { step: "any", min: -180, max: 180 } }}
                size="small"
                fullWidth
              />

              <ReadoutRow
                label="Latitude"
                value={sexResult?.latitude_display ?? "—"}
                onCopy={() =>
                  sexResult && copy(sexResult.latitude_display, "Latitude")
                }
                disabled={!sexResult}
              />
              <ReadoutRow
                label="Longitude"
                value={sexResult?.longitude_display ?? "—"}
                onCopy={() =>
                  sexResult && copy(sexResult.longitude_display, "Longitude")
                }
                disabled={!sexResult}
              />
            </Stack>
          </Paper>
        </Grid>

        {/* Panel B — Sexagesimal → Decimal */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2.5, height: "100%" }}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
              Sexagesimal → Decimal
            </Typography>
            <Stack spacing={2}>
              <TextField
                label="Latitude"
                value={latSex}
                onChange={(e) => setLatSex(e.target.value)}
                placeholder={"e.g. 33 27 54 N  or  33\u00B027'54\" N"}
                error={Boolean(decResult?.latitude_error)}
                helperText={
                  decResult?.latitude_error ??
                  "Accepts DMS, decimal, or hemisphere suffix"
                }
                size="small"
                fullWidth
              />
              <TextField
                label="Longitude"
                value={lonSex}
                onChange={(e) => setLonSex(e.target.value)}
                placeholder={"e.g. 112 04 26 W  or  112\u00B004'26\" W"}
                error={Boolean(decResult?.longitude_error)}
                helperText={
                  decResult?.longitude_error ??
                  "Accepts DMS, decimal, or hemisphere suffix"
                }
                size="small"
                fullWidth
              />

              <ReadoutRow
                label="Latitude"
                value={
                  decResult?.latitude != null
                    ? decResult.latitude.toFixed(6)
                    : "—"
                }
                onCopy={() =>
                  decResult?.latitude != null &&
                  copy(decResult.latitude.toFixed(6), "Latitude")
                }
                disabled={decResult?.latitude == null}
              />
              <ReadoutRow
                label="Longitude"
                value={
                  decResult?.longitude != null
                    ? decResult.longitude.toFixed(6)
                    : "—"
                }
                onCopy={() =>
                  decResult?.longitude != null &&
                  copy(decResult.longitude.toFixed(6), "Longitude")
                }
                disabled={decResult?.longitude == null}
              />
            </Stack>
          </Paper>
        </Grid>
      </Grid>

      <CalculatorAboutSection>
        <p>
          Conversions are performed server-side by{" "}
          <code>astropy.coordinates.Angle</code>, which accepts a range of
          input formats.
        </p>
        <p>Acceptable sexagesimal inputs include:</p>
        <ul>
          <li>
            <code>33 27 54 N</code>
          </li>
          <li>
            <code>33&deg;27&#39;54&quot; N</code>
          </li>
          <li>
            <code>33.465 N</code>
          </li>
          <li>
            <code>33.465</code> (sign indicates hemisphere)
          </li>
        </ul>
        <p>
          Hemisphere suffixes (<code>N</code>/<code>S</code> for latitude,{" "}
          <code>E</code>/<code>W</code> for longitude) override any leading sign.
        </p>
      </CalculatorAboutSection>

      <Snackbar
        open={snack !== null}
        autoHideDuration={2000}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="info" onClose={() => setSnack(null)}>
          {snack}
        </Alert>
      </Snackbar>
    </Stack>
  );
}

function ReadoutRow({
  label,
  value,
  onCopy,
  disabled,
}: {
  label: string;
  value: string;
  onCopy: () => void;
  disabled: boolean;
}) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1,
        borderTop: 1,
        borderColor: "divider",
        pt: 1.5,
      }}
    >
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ minWidth: 80 }}
      >
        {label}
      </Typography>
      <Typography
        variant="h6"
        sx={{ fontFamily: "monospace", flex: 1, wordBreak: "break-all" }}
      >
        {value}
      </Typography>
      <Tooltip title="Copy" arrow>
        <span>
          <IconButton size="small" onClick={onCopy} disabled={disabled}>
            <ContentCopyIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
    </Box>
  );
}
