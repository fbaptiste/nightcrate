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
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";

import {
  fetchFov,
  type FovRequest,
  type FovResponse,
} from "@/api/calculators";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import RigPickerMenu from "@/components/calculators/RigPickerMenu";
import { Block, Inline } from "@/components/calculators/Math";
import { useDebounce } from "@/lib/useDebounce";

type InputMode = "sensor" | "pixels";

function parseNumber(raw: string): number | null {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function formatDegMin(deg: number, arcmin: number): string {
  return `${deg.toFixed(3)}\u00B0 (${arcmin.toFixed(1)}\u2032)`;
}

interface ReadoutRowProps {
  label: string;
  display: string;
  copyText: string | null;
  onCopy: (text: string) => void;
}

function ReadoutRow({ label, display, copyText, onCopy }: ReadoutRowProps) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Stack direction="row" alignItems="center" spacing={1}>
        <Typography variant="body1" fontFamily="monospace" sx={{ fontSize: "1.1rem" }}>
          {display}
        </Typography>
        <Tooltip title={`Copy ${label.toLowerCase()}`}>
          <span>
            <IconButton
              size="small"
              onClick={() => copyText !== null && onCopy(copyText)}
              disabled={copyText === null}
              aria-label={`Copy ${label.toLowerCase()}`}
            >
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
    </Box>
  );
}

export default function FieldOfViewCalc() {
  const [mode, setMode] = useState<InputMode>("sensor");

  const [focalLength, setFocalLength] = useState<string>("540");
  const [sensorWidth, setSensorWidth] = useState<string>("23.5");
  const [sensorHeight, setSensorHeight] = useState<string>("15.7");
  const [pixelsX, setPixelsX] = useState<string>("6248");
  const [pixelsY, setPixelsY] = useState<string>("4176");
  const [pixelSize, setPixelSize] = useState<string>("3.76");

  const [response, setResponse] = useState<FovResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [snackOpen, setSnackOpen] = useState(false);

  const dFocal = useDebounce(focalLength, 200);
  const dSensorW = useDebounce(sensorWidth, 200);
  const dSensorH = useDebounce(sensorHeight, 200);
  const dPxX = useDebounce(pixelsX, 200);
  const dPxY = useDebounce(pixelsY, 200);
  const dPxSize = useDebounce(pixelSize, 200);
  const dMode = useDebounce(mode, 200);

  const request = useMemo<FovRequest | null>(() => {
    const f = parseNumber(dFocal);
    if (f === null || f <= 0) return null;
    if (dMode === "sensor") {
      const sw = parseNumber(dSensorW);
      const sh = parseNumber(dSensorH);
      if (sw === null || sh === null || sw <= 0 || sh <= 0) return null;
      return {
        focal_length_mm: f,
        sensor_width_mm: sw,
        sensor_height_mm: sh,
      };
    }
    const px = parseNumber(dPxX);
    const py = parseNumber(dPxY);
    const ps = parseNumber(dPxSize);
    if (
      px === null ||
      py === null ||
      ps === null ||
      px <= 0 ||
      py <= 0 ||
      ps <= 0
    ) {
      return null;
    }
    return {
      focal_length_mm: f,
      pixel_count_x: px,
      pixel_count_y: py,
      pixel_size_um: ps,
    };
  }, [dMode, dFocal, dSensorW, dSensorH, dPxX, dPxY, dPxSize]);

  useEffect(() => {
    if (request === null) {
      setError("Enter valid positive numbers for all fields.");
      return;
    }
    let cancelled = false;
    fetchFov(request)
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
  }, [request]);

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setSnackOpen(true);
    } catch {
      /* noop */
    }
  };

  const widthDisplay =
    response !== null
      ? formatDegMin(response.width_deg, response.width_arcmin)
      : "\u2014";
  const heightDisplay =
    response !== null
      ? formatDegMin(response.height_deg, response.height_arcmin)
      : "\u2014";
  const diagDisplay =
    response !== null
      ? formatDegMin(response.diagonal_deg, response.diagonal_arcmin)
      : "\u2014";

  return (
    <Stack spacing={3}>
      <Typography variant="h5">Field of View</Typography>

      <RigPickerMenu
        onApply={(rig) => {
          setFocalLength(String(rig.effective_focal_length_mm));
          setPixelSize(String(rig.pixel_size_um));
          setPixelsX(String(rig.sensor_resolution_x));
          setPixelsY(String(rig.sensor_resolution_y));
          if (rig.sensor_width_mm != null) {
            setSensorWidth(String(rig.sensor_width_mm));
          }
          if (rig.sensor_height_mm != null) {
            setSensorHeight(String(rig.sensor_height_mm));
          }
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
                <ToggleButtonGroup
                  value={mode}
                  exclusive
                  onChange={(_, next) => {
                    if (next !== null) setMode(next as InputMode);
                  }}
                  size="small"
                  color="primary"
                  fullWidth
                >
                  <ToggleButton value="sensor">
                    Sensor dimensions (mm)
                  </ToggleButton>
                  <ToggleButton value="pixels">
                    Pixel count + pixel size
                  </ToggleButton>
                </ToggleButtonGroup>

                <TextField
                  label="Focal length (mm)"
                  type="number"
                  value={focalLength}
                  onChange={(e) => setFocalLength(e.target.value)}
                  inputProps={{ step: "any", min: 0 }}
                  fullWidth
                />

                {mode === "sensor" ? (
                  <>
                    <TextField
                      label="Sensor width (mm)"
                      type="number"
                      value={sensorWidth}
                      onChange={(e) => setSensorWidth(e.target.value)}
                      inputProps={{ step: "any", min: 0 }}
                      fullWidth
                    />
                    <TextField
                      label="Sensor height (mm)"
                      type="number"
                      value={sensorHeight}
                      onChange={(e) => setSensorHeight(e.target.value)}
                      inputProps={{ step: "any", min: 0 }}
                      fullWidth
                    />
                  </>
                ) : (
                  <>
                    <TextField
                      label="Pixels X (count)"
                      type="number"
                      value={pixelsX}
                      onChange={(e) => setPixelsX(e.target.value)}
                      inputProps={{ step: 1, min: 0 }}
                      fullWidth
                    />
                    <TextField
                      label="Pixels Y (count)"
                      type="number"
                      value={pixelsY}
                      onChange={(e) => setPixelsY(e.target.value)}
                      inputProps={{ step: 1, min: 0 }}
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
                  </>
                )}
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
                <ReadoutRow
                  label="Width"
                  display={widthDisplay}
                  copyText={
                    response !== null
                      ? formatDegMin(
                          response.width_deg,
                          response.width_arcmin,
                        )
                      : null
                  }
                  onCopy={copy}
                />
                <ReadoutRow
                  label="Height"
                  display={heightDisplay}
                  copyText={
                    response !== null
                      ? formatDegMin(
                          response.height_deg,
                          response.height_arcmin,
                        )
                      : null
                  }
                  onCopy={copy}
                />
                <ReadoutRow
                  label="Diagonal"
                  display={diagDisplay}
                  copyText={
                    response !== null
                      ? formatDegMin(
                          response.diagonal_deg,
                          response.diagonal_arcmin,
                        )
                      : null
                  }
                  onCopy={copy}
                />
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
          {String.raw`\text{FOV} = 2 \arctan\!\left(\frac{\text{sensor dimension}}{2 \times \text{focal length}}\right)`}
        </Block>
        <Typography variant="body2">
          Diagonal is <Inline>{String.raw`\sqrt{w^2 + h^2}`}</Inline> —
          approximate but close for small fields.
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
