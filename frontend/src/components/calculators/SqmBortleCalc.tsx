import { useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import FormControl from "@mui/material/FormControl";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";

import { fetchSqmBortle } from "@/api/calculators";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import { useDebounce } from "@/lib/useDebounce";

type Field = "sqm" | "bortle" | "nelm";

interface BortleOption {
  value: number;
  label: string;
}

const BORTLE_LABELS: BortleOption[] = [
  { value: 1, label: "1 \u2014 Excellent dark-sky site" },
  { value: 2, label: "2 \u2014 Typical truly dark site" },
  { value: 3, label: "3 \u2014 Rural sky" },
  { value: 4, label: "4 \u2014 Rural / suburban transition" },
  { value: 5, label: "5 \u2014 Suburban sky" },
  { value: 6, label: "6 \u2014 Bright suburban sky" },
  { value: 7, label: "7 \u2014 Suburban / urban transition" },
  { value: 8, label: "8 \u2014 City sky" },
  { value: 9, label: "9 \u2014 Inner-city sky" },
];

function formatNumber(n: number | null | undefined, digits: number): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "";
  return n.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    useGrouping: false,
  });
}

async function copyText(text: string) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    /* noop */
  }
}

export default function SqmBortleCalc() {
  const [sqmText, setSqmText] = useState<string>("21.5");
  const [bortleValue, setBortleValue] = useState<number | "">(4);
  const [nelmText, setNelmText] = useState<string>("");
  const [lastEdited, setLastEdited] = useState<Field>("sqm");
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Track which field the user is actively editing so we don't clobber it
  // when the server response comes back.
  const lastEditedRef = useRef<Field>(lastEdited);
  lastEditedRef.current = lastEdited;

  const debouncedSqm = useDebounce(sqmText, 200);
  const debouncedBortle = useDebounce(bortleValue, 200);
  const debouncedNelm = useDebounce(nelmText, 200);

  useEffect(() => {
    const edited = lastEditedRef.current;

    // Parse only the field being edited; send a single-key payload.
    const payload: { sqm?: number; bortle?: number; nelm?: number } = {};
    if (edited === "sqm") {
      const n = Number(debouncedSqm);
      if (debouncedSqm.trim() === "" || !Number.isFinite(n)) return;
      payload.sqm = n;
    } else if (edited === "bortle") {
      if (debouncedBortle === "" || !Number.isFinite(Number(debouncedBortle)))
        return;
      payload.bortle = Number(debouncedBortle);
    } else if (edited === "nelm") {
      const n = Number(debouncedNelm);
      if (debouncedNelm.trim() === "" || !Number.isFinite(n)) return;
      payload.nelm = n;
    }

    let cancelled = false;
    fetchSqmBortle(payload)
      .then((res) => {
        if (cancelled) return;
        // Overwrite the two NON-edited fields only; leave the edited one alone
        // so the user's in-flight typing isn't clobbered.
        if (edited !== "sqm") {
          setSqmText(formatNumber(res.sqm, 2));
        }
        if (edited !== "bortle") {
          setBortleValue(res.bortle === null ? "" : Math.round(res.bortle));
        }
        if (edited !== "nelm") {
          setNelmText(formatNumber(res.nelm, 2));
        }
        setNote(res.note);
        setError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setError("Conversion failed, check input");
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedSqm, debouncedBortle, debouncedNelm]);

  const handleSqmChange = (value: string) => {
    setLastEdited("sqm");
    setSqmText(value);
  };
  const handleBortleChange = (value: number | "") => {
    setLastEdited("bortle");
    setBortleValue(value);
  };
  const handleNelmChange = (value: string) => {
    setLastEdited("nelm");
    setNelmText(value);
  };

  return (
    <Stack spacing={3}>
      <Typography variant="h5">SQM / Bortle / NELM</Typography>

      <Alert severity="info">
        These conversions are approximate. Bortle is originally a qualitative
        visual scale; NELM depends on the observer&rsquo;s visual acuity.
      </Alert>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                SQM
              </Typography>
              <TextField
                label="mag/arcsec\u00B2"
                type="number"
                value={sqmText}
                onChange={(e) => handleSqmChange(e.target.value)}
                fullWidth
                inputProps={{ step: "0.01" }}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <Tooltip title="Copy SQM">
                        <span>
                          <IconButton
                            size="small"
                            aria-label="Copy SQM"
                            onClick={() => copyText(sqmText)}
                            disabled={!sqmText}
                          >
                            <ContentCopyIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </InputAdornment>
                  ),
                }}
              />
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: 1, display: "block" }}
              >
                Typical: 16&ndash;22
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 4 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Bortle Class
              </Typography>
              <FormControl fullWidth>
                <InputLabel id="bortle-select-label">Class</InputLabel>
                <Select
                  labelId="bortle-select-label"
                  label="Class"
                  value={bortleValue === "" ? "" : String(bortleValue)}
                  onChange={(e) => {
                    const raw = e.target.value;
                    handleBortleChange(raw === "" ? "" : Number(raw));
                  }}
                >
                  {BORTLE_LABELS.map((opt) => (
                    <MenuItem key={opt.value} value={String(opt.value)}>
                      {opt.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: 1, display: "block" }}
              >
                Classes 1&ndash;9
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 4 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                NELM
              </Typography>
              <TextField
                label="mag"
                type="number"
                value={nelmText}
                onChange={(e) => handleNelmChange(e.target.value)}
                fullWidth
                inputProps={{ step: "0.1" }}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <Tooltip title="Copy NELM">
                        <span>
                          <IconButton
                            size="small"
                            aria-label="Copy NELM"
                            onClick={() => copyText(nelmText)}
                            disabled={!nelmText}
                          >
                            <ContentCopyIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </InputAdornment>
                  ),
                }}
              />
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: 1, display: "block" }}
              >
                Typical: 3.5&ndash;7.8
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {note && <Alert severity="warning">{note}</Alert>}
      {error && <Alert severity="error">{error}</Alert>}

      <CalculatorAboutSection>
        <Typography variant="body2" component="p">
          SQM &rarr; Bortle uses the standard band mapping (see Bortle 2001
          / community tables). SQM &harr; NELM uses Schaefer&rsquo;s
          approximation:{" "}
          <code>
            NELM &asymp; 7.93 &minus; 5 &times; log10(10^(4.316 &minus; SQM/5)
            + 1)
          </code>
          . These are rough conversions &mdash; NELM especially varies with
          observer visual acuity.
        </Typography>
      </CalculatorAboutSection>
    </Stack>
  );
}
