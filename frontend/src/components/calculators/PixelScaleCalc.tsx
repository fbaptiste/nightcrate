import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";

import {
  fetchPixelScale,
  type PixelScaleResponse,
} from "@/api/calculators";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import RigPickerMenu from "@/components/calculators/RigPickerMenu";
import { Block } from "@/components/calculators/Math";
import { useDebounce } from "@/lib/useDebounce";

function parseNumber(raw: string): number | null {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export default function PixelScaleCalc() {
  const [focalLength, setFocalLength] = useState<string>("540");
  const [pixelSize, setPixelSize] = useState<string>("3.76");
  const [reducer, setReducer] = useState<string>("1.0");

  const [response, setResponse] = useState<PixelScaleResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [snackOpen, setSnackOpen] = useState(false);

  const dFocal = useDebounce(focalLength, 200);
  const dPixel = useDebounce(pixelSize, 200);
  const dReducer = useDebounce(reducer, 200);

  const parsed = useMemo(() => {
    const f = parseNumber(dFocal);
    const p = parseNumber(dPixel);
    const r = parseNumber(dReducer);
    if (f === null || p === null || r === null) return null;
    if (f <= 0 || p <= 0 || r <= 0) return null;
    return { f, p, r };
  }, [dFocal, dPixel, dReducer]);

  useEffect(() => {
    if (parsed === null) {
      setError("Enter valid positive numbers for all fields.");
      return;
    }
    let cancelled = false;
    fetchPixelScale(parsed.f, parsed.p, parsed.r)
      .then((res) => {
        if (cancelled) return;
        setResponse(res);
        setError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setError("Calculation failed, check inputs.");
      });
    return () => {
      cancelled = true;
    };
  }, [parsed]);

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setSnackOpen(true);
    } catch {
      /* noop */
    }
  };

  const arcsecDisplay =
    response !== null ? `${response.arcsec_per_pixel.toFixed(3)}\u2033/px` : "\u2014";
  const effectiveFocalDisplay =
    response !== null
      ? `${response.effective_focal_length_mm.toFixed(1)} mm`
      : "\u2014";

  return (
    <Stack spacing={3}>
      <Typography variant="h5">Pixel Scale</Typography>

      <RigPickerMenu
        onApply={(rig) => {
          setFocalLength(String(rig.effective_focal_length_mm));
          setPixelSize(String(rig.pixel_size_um));
          setReducer("1.0");
        }}
      />

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 2 }}>
                Inputs
              </Typography>
              <Stack spacing={2}>
                <TextField
                  label="Focal length (mm)"
                  type="number"
                  value={focalLength}
                  onChange={(e) => setFocalLength(e.target.value)}
                  inputProps={{ step: "any", min: 0 }}
                  fullWidth
                />
                <TextField
                  label={"Pixel size (\u00B5m)"}
                  type="number"
                  value={pixelSize}
                  onChange={(e) => setPixelSize(e.target.value)}
                  inputProps={{ step: "any", min: 0 }}
                  fullWidth
                />
                <TextField
                  label="Reducer / extender factor"
                  type="number"
                  value={reducer}
                  onChange={(e) => setReducer(e.target.value)}
                  inputProps={{ step: "any", min: 0 }}
                  helperText={
                    "Effective focal length = focal \u00D7 factor. " +
                    "Use 0.7 for a 0.7\u00D7 reducer, 1.5 for a 1.5\u00D7 extender."
                  }
                  fullWidth
                />
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
              <Stack spacing={2}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Image scale
                  </Typography>
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <Typography
                      variant="h4"
                      fontFamily="monospace"
                      aria-label="Arcseconds per pixel"
                    >
                      {arcsecDisplay}
                    </Typography>
                    <Tooltip title="Copy image scale">
                      <span>
                        <IconButton
                          size="small"
                          onClick={() =>
                            response !== null &&
                            copy(response.arcsec_per_pixel.toFixed(3))
                          }
                          disabled={response === null}
                          aria-label="Copy image scale"
                        >
                          <ContentCopyIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </Stack>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Effective focal length
                  </Typography>
                  <Typography variant="body1" fontFamily="monospace">
                    {effectiveFocalDisplay}
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <CalculatorAboutSection>
        <Typography variant="body2" sx={{ mb: 1 }}>
          <strong>Formula:</strong>
        </Typography>
        <Block>
          {String.raw`\text{arcsec/pixel} = \frac{\text{pixel size (}\mu\text{m)}}{\text{effective focal length (mm)}} \times 206.265`}
        </Block>
        <Typography variant="body2">
          Standard astrophotography rule of thumb: sample at 1.5&ndash;3&times;FWHM for
          well-sampled imaging; 2&ndash;4&times;FWHM is typical at suburban
          seeing (~3&Prime;).
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
