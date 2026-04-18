import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";

import {
  convertAngular,
  type AngularConvertResponse,
  type AngularUnit,
} from "@/api/calculators";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import { useDebounce } from "@/lib/useDebounce";

interface UnitDef {
  id: AngularUnit;
  label: string;
}

const UNITS: UnitDef[] = [
  { id: "rad", label: "Radians (rad)" },
  { id: "deg", label: "Degrees (\u00B0)" },
  { id: "arcmin", label: "Arcminutes (\u2032)" },
  { id: "arcsec", label: "Arcseconds (\u2033)" },
  { id: "mas", label: "Milliarcseconds (mas)" },
];

function formatNumber(n: number): string {
  if (!Number.isFinite(n)) return String(n);
  const abs = Math.abs(n);
  if (abs !== 0 && (abs > 1e6 || abs < 1e-3)) {
    return n.toExponential(6);
  }
  return n.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

export default function AngularUnitsCalc() {
  const [valueInput, setValueInput] = useState<string>("1");
  const [fromUnit, setFromUnit] = useState<AngularUnit>(UNITS[0].id);
  const [toUnit, setToUnit] = useState<AngularUnit>(UNITS[1].id);
  const [response, setResponse] = useState<AngularConvertResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const debouncedInput = useDebounce(valueInput, 200);
  const parsedValue = useMemo(() => {
    const n = Number(debouncedInput);
    return Number.isFinite(n) ? n : null;
  }, [debouncedInput]);

  useEffect(() => {
    if (parsedValue === null) {
      setError("Conversion failed, check input");
      return;
    }
    let cancelled = false;
    convertAngular(parsedValue, fromUnit, toUnit)
      .then((res) => {
        if (cancelled) return;
        setResponse(res);
        setError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setError("Conversion failed, check input");
      });
    return () => {
      cancelled = true;
    };
  }, [parsedValue, fromUnit, toUnit]);

  const swapUnits = () => {
    setFromUnit(toUnit);
    setToUnit(fromUnit);
  };

  const copyResult = async () => {
    if (response === null) return;
    try {
      await navigator.clipboard.writeText(String(response.result));
    } catch {
      /* noop */
    }
  };

  const resultDisplay = response ? formatNumber(response.result) : "\u2014";
  const toLabel = UNITS.find((u) => u.id === toUnit)?.label ?? toUnit;

  return (
    <Stack spacing={3}>
      <Typography variant="h5">Angular Units</Typography>

      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        alignItems={{ xs: "stretch", sm: "center" }}
      >
        <TextField
          label="Value"
          type="number"
          value={valueInput}
          onChange={(e) => setValueInput(e.target.value)}
          sx={{ minWidth: 200 }}
          inputProps={{ step: "any" }}
        />
        <FormControl sx={{ minWidth: 220 }}>
          <InputLabel id="angular-from-label">From</InputLabel>
          <Select
            labelId="angular-from-label"
            label="From"
            value={fromUnit}
            onChange={(e) => setFromUnit(e.target.value as AngularUnit)}
          >
            {UNITS.map((u) => (
              <MenuItem key={u.id} value={u.id}>
                {u.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Tooltip title="Swap units">
          <IconButton onClick={swapUnits} size="small" aria-label="Swap units">
            <SwapHorizIcon />
          </IconButton>
        </Tooltip>
        <Typography sx={{ mx: 1 }}>&rarr;</Typography>
        <FormControl sx={{ minWidth: 220 }}>
          <InputLabel id="angular-to-label">To</InputLabel>
          <Select
            labelId="angular-to-label"
            label="To"
            value={toUnit}
            onChange={(e) => setToUnit(e.target.value as AngularUnit)}
          >
            {UNITS.map((u) => (
              <MenuItem key={u.id} value={u.id}>
                {u.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Typography
          variant="h6"
          fontFamily="monospace"
          sx={{ ml: { sm: 1 }, minWidth: 160 }}
          aria-label={`Result in ${toLabel}`}
        >
          {resultDisplay}
        </Typography>
        <Tooltip title="Copy result">
          <span>
            <IconButton
              onClick={copyResult}
              size="small"
              disabled={response === null}
              aria-label="Copy result"
            >
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>

      {error && <Alert severity="warning">{error}</Alert>}

      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            All units
          </Typography>
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "auto 1fr",
              gap: 1,
              columnGap: 3,
            }}
          >
            {UNITS.map((u) => (
              <Box key={u.id} sx={{ display: "contents" }}>
                <Typography variant="body2" color="text.secondary">
                  {u.label}:
                </Typography>
                <Typography variant="body2" fontFamily="monospace">
                  {response ? formatNumber(response.all_units[u.id]) : "\u2014"}
                </Typography>
              </Box>
            ))}
          </Box>
        </CardContent>
      </Card>

      <CalculatorAboutSection>
        <Typography variant="body2">
          Converts between common angular measures used in astronomy.
          One full turn equals 2&pi; radians or 360&deg;. A degree
          contains 60 arcminutes (&prime;), an arcminute contains 60
          arcseconds (&Prime;), and one arcsecond equals 1000
          milliarcseconds (mas). Arcseconds and milliarcseconds are the
          native units of pixel scale and astrometric precision; degrees
          and arcminutes are common for field-of-view measurements;
          radians are the SI base unit used in underlying math.
        </Typography>
      </CalculatorAboutSection>
    </Stack>
  );
}
