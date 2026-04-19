import { useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";

import { fetchTemperature, type TemperatureUnit } from "@/api/calculators";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import { Block } from "@/components/calculators/Math";
import { useDebounce } from "@/lib/useDebounce";

type Field = "C" | "F" | "K";

function formatTemp(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "";
  return n.toLocaleString(undefined, {
    maximumFractionDigits: 2,
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

export default function TemperatureCalc() {
  const [celsius, setCelsius] = useState<string>("20");
  const [fahrenheit, setFahrenheit] = useState<string>("");
  const [kelvin, setKelvin] = useState<string>("");
  const [lastEdited, setLastEdited] = useState<Field>("C");
  const [error, setError] = useState<string | null>(null);

  const lastEditedRef = useRef<Field>(lastEdited);
  lastEditedRef.current = lastEdited;

  const debouncedC = useDebounce(celsius, 200);
  const debouncedF = useDebounce(fahrenheit, 200);
  const debouncedK = useDebounce(kelvin, 200);

  useEffect(() => {
    const edited = lastEditedRef.current;
    let raw: string;
    if (edited === "C") raw = debouncedC;
    else if (edited === "F") raw = debouncedF;
    else raw = debouncedK;

    if (raw.trim() === "") return;
    const n = Number(raw);
    if (!Number.isFinite(n)) {
      setError("Conversion failed, check input");
      return;
    }

    let cancelled = false;
    fetchTemperature(n, edited as TemperatureUnit)
      .then((res) => {
        if (cancelled) return;
        // Overwrite the two NON-edited fields only.
        if (edited !== "C") setCelsius(formatTemp(res.celsius));
        if (edited !== "F") setFahrenheit(formatTemp(res.fahrenheit));
        if (edited !== "K") setKelvin(formatTemp(res.kelvin));
        setError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setError("Conversion failed, check input");
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedC, debouncedF, debouncedK]);

  const handleChange = (field: Field, value: string) => {
    setLastEdited(field);
    if (field === "C") setCelsius(value);
    else if (field === "F") setFahrenheit(value);
    else setKelvin(value);
  };

  return (
    <Stack spacing={3}>
      <Typography variant="h5">Temperature</Typography>

      <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        <TextField
          label={"\u00B0C"}
          type="number"
          value={celsius}
          onChange={(e) => handleChange("C", e.target.value)}
          sx={{ flex: 1 }}
          inputProps={{ step: "any" }}
          InputProps={{
            endAdornment: (
              <InputAdornment position="end">
                <Tooltip title={"Copy \u00B0C"}>
                  <span>
                    <IconButton
                      size="small"
                      aria-label="Copy Celsius"
                      onClick={() => copyText(celsius)}
                      disabled={!celsius}
                    >
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              </InputAdornment>
            ),
          }}
        />
        <TextField
          label={"\u00B0F"}
          type="number"
          value={fahrenheit}
          onChange={(e) => handleChange("F", e.target.value)}
          sx={{ flex: 1 }}
          inputProps={{ step: "any" }}
          InputProps={{
            endAdornment: (
              <InputAdornment position="end">
                <Tooltip title={"Copy \u00B0F"}>
                  <span>
                    <IconButton
                      size="small"
                      aria-label="Copy Fahrenheit"
                      onClick={() => copyText(fahrenheit)}
                      disabled={!fahrenheit}
                    >
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              </InputAdornment>
            ),
          }}
        />
        <TextField
          label="K"
          type="number"
          value={kelvin}
          onChange={(e) => handleChange("K", e.target.value)}
          sx={{ flex: 1 }}
          inputProps={{ step: "any" }}
          InputProps={{
            endAdornment: (
              <InputAdornment position="end">
                <Tooltip title="Copy K">
                  <span>
                    <IconButton
                      size="small"
                      aria-label="Copy Kelvin"
                      onClick={() => copyText(kelvin)}
                      disabled={!kelvin}
                    >
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              </InputAdornment>
            ),
          }}
        />
      </Stack>

      <Typography variant="body2" color="text.secondary">
        Useful for matching dark frames by sensor temperature, where capture
        software may report in either &deg;C or &deg;F.
      </Typography>

      {error && <Alert severity="warning">{error}</Alert>}

      <CalculatorAboutSection>
        <Block>
          {String.raw`C = (F - 32) \times \tfrac{5}{9} = K - 273.15`}
        </Block>
        <Typography variant="body2" component="p">
          Formulas are exact; all rounding happens at display.
        </Typography>
      </CalculatorAboutSection>
    </Stack>
  );
}
