import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import ListSubheader from "@mui/material/ListSubheader";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";

import {
  convertLinear,
  type LinearConvertResponse,
  type LinearUnit,
} from "@/api/calculators";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import { useDebounce } from "@/lib/useDebounce";

interface UnitDef {
  id: LinearUnit;
  label: string;
}

interface UnitGroup {
  name: string;
  units: UnitDef[];
}

const GROUPS: UnitGroup[] = [
  {
    name: "Small",
    units: [
      { id: "nm", label: "Nanometers (nm)" },
      { id: "um", label: "Micrometers (\u00B5m)" },
      { id: "mm", label: "Millimeters (mm)" },
      { id: "cm", label: "Centimeters (cm)" },
      { id: "m", label: "Meters (m)" },
      { id: "in", label: "Inches (in)" },
      { id: "ft", label: "Feet (ft)" },
      { id: "yd", label: "Yards (yd)" },
    ],
  },
  {
    name: "Human/Earth",
    units: [
      { id: "km", label: "Kilometers (km)" },
      { id: "mi", label: "Miles (mi)" },
      { id: "nmi", label: "Nautical miles (nmi)" },
    ],
  },
  {
    name: "Astronomical",
    units: [
      { id: "au", label: "Astronomical units (AU)" },
      { id: "ly", label: "Light-years (ly)" },
      { id: "pc", label: "Parsecs (pc)" },
      { id: "kpc", label: "Kiloparsecs (kpc)" },
      { id: "mpc", label: "Megaparsecs (Mpc)" },
    ],
  },
];

const ALL_UNITS: UnitDef[] = GROUPS.flatMap((g) => g.units);
const UNIT_BY_ID: Record<LinearUnit, UnitDef> = ALL_UNITS.reduce(
  (acc, u) => {
    acc[u.id] = u;
    return acc;
  },
  {} as Record<LinearUnit, UnitDef>,
);

function renderGroupedMenuItems() {
  const items: React.ReactNode[] = [];
  for (const group of GROUPS) {
    items.push(
      <ListSubheader key={`hdr-${group.name}`}>{group.name}</ListSubheader>,
    );
    for (const u of group.units) {
      items.push(
        <MenuItem key={u.id} value={u.id}>
          {u.label}
        </MenuItem>,
      );
    }
  }
  return items;
}

function formatNumber(n: number): string {
  if (!Number.isFinite(n)) return String(n);
  const abs = Math.abs(n);
  if (abs !== 0 && (abs > 1e6 || abs < 1e-3)) {
    return n.toExponential(6);
  }
  return n.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

export default function LinearUnitsCalc() {
  const [valueInput, setValueInput] = useState<string>("1");
  const [fromUnit, setFromUnit] = useState<LinearUnit>(ALL_UNITS[0].id);
  const [toUnit, setToUnit] = useState<LinearUnit>(ALL_UNITS[1].id);
  const [response, setResponse] = useState<LinearConvertResponse | null>(null);
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
    convertLinear(parsedValue, fromUnit, toUnit)
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
  const toLabel = UNIT_BY_ID[toUnit]?.label ?? toUnit;

  return (
    <Stack spacing={3}>
      <Typography variant="h5">Linear Units</Typography>

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
        <FormControl sx={{ minWidth: 240 }}>
          <InputLabel id="linear-from-label">From</InputLabel>
          <Select
            labelId="linear-from-label"
            label="From"
            value={fromUnit}
            onChange={(e) => setFromUnit(e.target.value as LinearUnit)}
          >
            {renderGroupedMenuItems()}
          </Select>
        </FormControl>
        <Tooltip title="Swap units">
          <IconButton onClick={swapUnits} size="small" aria-label="Swap units">
            <SwapHorizIcon />
          </IconButton>
        </Tooltip>
        <Typography sx={{ mx: 1 }}>&rarr;</Typography>
        <FormControl sx={{ minWidth: 240 }}>
          <InputLabel id="linear-to-label">To</InputLabel>
          <Select
            labelId="linear-to-label"
            label="To"
            value={toUnit}
            onChange={(e) => setToUnit(e.target.value as LinearUnit)}
          >
            {renderGroupedMenuItems()}
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
            {ALL_UNITS.map((u) => (
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
          Converts between metric, imperial, and astronomical distance
          units. Metric units follow SI prefixes; imperial definitions
          use the international foot (1 ft = 0.3048 m). Astronomical
          units use IAU 2012/2015 definitions: 1 AU = 149&thinsp;597&thinsp;870.7 km,
          1 light-year = 9.4607&times;10<sup>15</sup> m, 1 parsec =
          648&thinsp;000/&pi; AU {"\u2248"} 3.0857&times;10<sup>16</sup> m.
          Kiloparsecs (kpc) and megaparsecs (Mpc) are used for galactic
          and extragalactic scales.
        </Typography>
      </CalculatorAboutSection>
    </Stack>
  );
}
