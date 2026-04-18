import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import FormControl from "@mui/material/FormControl";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";

import {
  fetchFileSize,
  type FileSizeResponse,
} from "@/api/calculators";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import { useDebounce } from "@/lib/useDebounce";
import { RIG_ORANGE } from "@/lib/rigColors";

const TEN_GB_IN_BYTES = 10 * 1024 * 1024 * 1024;

function parseNumber(raw: string): number | null {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export default function FileSizeCalc() {
  const [width, setWidth] = useState<string>("6248");
  const [height, setHeight] = useState<string>("4176");
  const [bitDepth, setBitDepth] = useState<number>(16);
  const [frames, setFrames] = useState<string>("1");
  const [compression, setCompression] = useState<string>("1.0");

  const [response, setResponse] = useState<FileSizeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [snackOpen, setSnackOpen] = useState(false);

  const dWidth = useDebounce(width, 200);
  const dHeight = useDebounce(height, 200);
  const dBitDepth = useDebounce(bitDepth, 200);
  const dFrames = useDebounce(frames, 200);
  const dCompression = useDebounce(compression, 200);

  const parsed = useMemo(() => {
    const w = parseNumber(dWidth);
    const h = parseNumber(dHeight);
    const n = parseNumber(dFrames);
    const c = parseNumber(dCompression);
    if (w === null || h === null || n === null || c === null) return null;
    if (w <= 0 || h <= 0 || n <= 0 || c <= 0) return null;
    return { w, h, n, c };
  }, [dWidth, dHeight, dFrames, dCompression]);

  useEffect(() => {
    if (parsed === null) {
      setError("Enter valid positive numbers for all fields.");
      return;
    }
    let cancelled = false;
    fetchFileSize(parsed.w, parsed.h, dBitDepth, parsed.n, parsed.c)
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
  }, [parsed, dBitDepth]);

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setSnackOpen(true);
    } catch {
      /* noop */
    }
  };

  const megapixels = response !== null ? response.megapixels.toFixed(2) : "\u2014";
  const perFrameDisplay = response !== null ? response.per_frame_display : "\u2014";
  const totalDisplay = response !== null ? response.total_display : "\u2014";
  const totalHighlight =
    response !== null && response.total_bytes > TEN_GB_IN_BYTES;

  return (
    <Stack spacing={3}>
      <Typography variant="h5">File Size Estimator</Typography>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 2 }}>
                Inputs
              </Typography>
              <Stack spacing={2}>
                <TextField
                  label="Image width (px)"
                  type="number"
                  value={width}
                  onChange={(e) => setWidth(e.target.value)}
                  inputProps={{ step: 1, min: 0 }}
                  fullWidth
                />
                <TextField
                  label="Image height (px)"
                  type="number"
                  value={height}
                  onChange={(e) => setHeight(e.target.value)}
                  inputProps={{ step: 1, min: 0 }}
                  fullWidth
                />
                <FormControl fullWidth>
                  <InputLabel id="file-size-bit-depth-label">
                    Bit depth
                  </InputLabel>
                  <Select
                    labelId="file-size-bit-depth-label"
                    label="Bit depth"
                    value={bitDepth}
                    onChange={(e) => setBitDepth(Number(e.target.value))}
                  >
                    <MenuItem value={8}>8-bit</MenuItem>
                    <MenuItem value={16}>16-bit</MenuItem>
                    <MenuItem value={32}>32-bit</MenuItem>
                  </Select>
                </FormControl>
                <TextField
                  label="Number of frames"
                  type="number"
                  value={frames}
                  onChange={(e) => setFrames(e.target.value)}
                  inputProps={{ step: 1, min: 0 }}
                  fullWidth
                />
                <TextField
                  label="Compression factor"
                  type="number"
                  value={compression}
                  onChange={(e) => setCompression(e.target.value)}
                  inputProps={{ step: "any", min: 0 }}
                  helperText="Use ~0.6 for RICE-compressed FITS, 1.0 for uncompressed."
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
                    Megapixels
                  </Typography>
                  <Typography variant="body1" fontFamily="monospace">
                    {megapixels}
                  </Typography>
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Per frame
                  </Typography>
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <Typography variant="h5" fontFamily="monospace">
                      {perFrameDisplay}
                    </Typography>
                    <Tooltip title="Copy per-frame size">
                      <span>
                        <IconButton
                          size="small"
                          onClick={() =>
                            response !== null &&
                            copy(response.per_frame_display)
                          }
                          disabled={response === null}
                          aria-label="Copy per-frame size"
                        >
                          <ContentCopyIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </Stack>
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Total
                  </Typography>
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <Typography
                      variant="h4"
                      fontFamily="monospace"
                      sx={totalHighlight ? { color: RIG_ORANGE } : undefined}
                    >
                      {totalDisplay}
                    </Typography>
                    <Tooltip title="Copy total size">
                      <span>
                        <IconButton
                          size="small"
                          onClick={() =>
                            response !== null && copy(response.total_display)
                          }
                          disabled={response === null}
                          aria-label="Copy total size"
                        >
                          <ContentCopyIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </Stack>
                  {totalHighlight && (
                    <Typography
                      variant="caption"
                      sx={{ color: RIG_ORANGE, display: "block", mt: 0.5 }}
                    >
                      Exceeds 10 GB &mdash; plan storage accordingly.
                    </Typography>
                  )}
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <CalculatorAboutSection>
        <Typography variant="body2">
          <strong>Formula:</strong> bytes/frame = width &times; height &times;
          (bit_depth / 8) &times; compression. RICE/LZW typically reduce FITS
          to 50&ndash;70% of raw; set compression &approx; 0.6 to model that.
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
