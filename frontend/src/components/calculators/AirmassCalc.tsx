import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import Slider from "@mui/material/Slider";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";

import {
  fetchAirmass,
  type AirmassResponse,
} from "@/api/calculators";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import { Block, Inline } from "@/components/calculators/Math";
import { useDebounce } from "@/lib/useDebounce";

function parseNumber(raw: string): number | null {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function clampAltitude(v: number): number {
  if (v < 0) return 0;
  if (v > 90) return 90;
  return v;
}

export default function AirmassCalc() {
  const [altitudeRaw, setAltitudeRaw] = useState<string>("45");

  const [response, setResponse] = useState<AirmassResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [snackOpen, setSnackOpen] = useState(false);

  const dAltitude = useDebounce(altitudeRaw, 200);

  const parsedAltitude = useMemo(() => {
    const n = parseNumber(dAltitude);
    if (n === null) return null;
    if (n < 0 || n > 90) return null;
    return n;
  }, [dAltitude]);

  useEffect(() => {
    if (parsedAltitude === null) {
      setError("Enter an altitude between 0 and 90 degrees.");
      return;
    }
    let cancelled = false;
    fetchAirmass(parsedAltitude)
      .then((res) => {
        if (cancelled) return;
        setResponse(res);
        setError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setError("Calculation failed, check input.");
      });
    return () => {
      cancelled = true;
    };
  }, [parsedAltitude]);

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setSnackOpen(true);
    } catch {
      /* noop */
    }
  };

  const sliderValue = (() => {
    const n = parseNumber(altitudeRaw);
    if (n === null) return 45;
    return clampAltitude(n);
  })();

  const airmassText = (() => {
    if (response === null) return "\u2014";
    if (response.below_horizon) return "Below horizon";
    if (response.airmass === null) return "\u2014";
    return response.airmass.toFixed(3);
  })();
  const canCopy =
    response !== null && !response.below_horizon && response.airmass !== null;

  return (
    <Stack spacing={3}>
      <Typography variant="h5">Airmass</Typography>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 2 }}>
                Inputs
              </Typography>
              <Stack spacing={2}>
                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={2}
                  alignItems={{ xs: "stretch", sm: "center" }}
                >
                  <TextField
                    label={"Altitude (\u00B0)"}
                    type="number"
                    value={altitudeRaw}
                    onChange={(e) => setAltitudeRaw(e.target.value)}
                    inputProps={{ step: "any", min: 0, max: 90 }}
                    sx={{ minWidth: 160 }}
                  />
                  <Slider
                    value={sliderValue}
                    min={0}
                    max={90}
                    step={0.5}
                    marks={[
                      { value: 0, label: "0\u00B0" },
                      { value: 30, label: "30\u00B0" },
                      { value: 60, label: "60\u00B0" },
                      { value: 90, label: "90\u00B0" },
                    ]}
                    onChange={(_, v) => {
                      if (typeof v === "number") {
                        setAltitudeRaw(String(v));
                      }
                    }}
                    sx={{ flex: 1 }}
                    aria-label="Altitude slider"
                  />
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  Altitude is measured above the horizon. 0&deg; = horizon,
                  90&deg; = zenith.
                </Typography>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 2 }}>
                Results
              </Typography>
              {error && (
                <Alert severity="warning" sx={{ mb: 2 }}>
                  {error}
                </Alert>
              )}
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Airmass
                </Typography>
                <Stack direction="row" alignItems="center" spacing={1}>
                  {response?.below_horizon ? (
                    <Typography variant="body1">{airmassText}</Typography>
                  ) : (
                    <Typography
                      variant="h4"
                      fontFamily="monospace"
                      aria-label="Airmass value"
                    >
                      {airmassText}
                    </Typography>
                  )}
                  <Tooltip title="Copy airmass">
                    <span>
                      <IconButton
                        size="small"
                        onClick={() =>
                          canCopy &&
                          response !== null &&
                          response.airmass !== null &&
                          copy(response.airmass.toFixed(3))
                        }
                        disabled={!canCopy}
                        aria-label="Copy airmass"
                      >
                        <ContentCopyIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                </Stack>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Reference
              </Typography>
              <Box
                sx={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr",
                  columnGap: 3,
                  rowGap: 0.5,
                  maxWidth: 280,
                }}
              >
                <Typography variant="caption" color="text.secondary">
                  Altitude &deg;
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Airmass
                </Typography>
                {response?.reference_table.map((row) => (
                  <Box
                    key={row.altitude_deg}
                    sx={{ display: "contents" }}
                  >
                    <Typography variant="body2" fontFamily="monospace">
                      {row.altitude_deg.toFixed(0)}
                    </Typography>
                    <Typography variant="body2" fontFamily="monospace">
                      {row.airmass.toFixed(3)}
                    </Typography>
                  </Box>
                ))}
                {response === null && (
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ gridColumn: "1 / span 2" }}
                  >
                    {"\u2014"}
                  </Typography>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <CalculatorAboutSection>
        <Typography variant="body2" sx={{ mb: 1 }}>
          <strong>Kasten-Young (1989) formula:</strong>
        </Typography>
        <Block>
          {String.raw`X = \frac{1}{\cos z + 0.50572 \, (6.07995 + 90 - z)^{-1.6364}}`}
        </Block>
        <Typography variant="body2">
          where <Inline>{String.raw`z`}</Inline> is the zenith angle in
          degrees. Valid across the full sky down to the horizon; more
          accurate than the plane-parallel{" "}
          <Inline>{String.raw`\sec z`}</Inline> approximation.
        </Typography>
      </CalculatorAboutSection>

      <Snackbar
        open={snackOpen}
        autoHideDuration={1500}
        onClose={() => setSnackOpen(false)}
        message="Copied to clipboard"
      />
    </Stack>
  );
}
