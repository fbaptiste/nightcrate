import { useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormLabel from "@mui/material/FormLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useQueryClient } from "@tanstack/react-query";
import type { Location } from "@/api/locations";
import type { WeatherUnits } from "@/api/settings";
import {
  fetchImagingRules,
  saveImagingRules,
  type CloudModel,
  type ImagingRules,
  type ImagingRulesPreset,
} from "@/api/weather";

type NumericField = {
  [K in keyof ImagingRules]: ImagingRules[K] extends number | null ? K : never
}[keyof ImagingRules];
type ValidationKey = NumericField | "cloud_models" | "cloud_preferred_model";

interface PreviewCounts {
  go: number;
  uncertain: number;
  no: number;
  notEnough: number;
}

const KMH_PER_MPH = 1.609344;
const MM_PER_INCH = 25.4;
const CLOUD_MODELS: Array<{
  key: CloudModel;
  label: string;
  field: "cloud_use_ecmwf" | "cloud_use_gfs" | "cloud_use_icon";
  note: string;
}> = [
  {
    key: "ecmwf_ifs025",
    label: "ECMWF",
    field: "cloud_use_ecmwf",
    note: "The European Centre's global model has the same detail everywhere, about 25 km. It reaches about 14 days ahead.",
  },
  {
    key: "gfs_seamless",
    label: "GFS",
    field: "cloud_use_gfs",
    note: "NOAA's global model has about 13 km detail, finer over the contiguous US for the first day or two. It reaches about 15 days ahead.",
  },
  {
    key: "icon_seamless",
    label: "ICON",
    field: "cloud_use_icon",
    note: "The German Weather Service's global model has about 11 km detail, finer over Europe for 5 days and finest over central Europe for 2. It reaches almost 7 days ahead.",
  },
];

function NoteTooltip({ note, children }: { note: string; children: React.ReactElement }) {
  return (
    <Tooltip
      arrow
      placement="top-start"
      enterDelay={300}
      enterTouchDelay={0}
      describeChild
      title={note}
    >
      {children}
    </Tooltip>
  );
}

function LabelNote({ label, note }: { label: string; note: string }) {
  return (
    <NoteTooltip note={note}>
      <span>{label}</span>
    </NoteTooltip>
  );
}

function windForDisplay(valueKmh: number): number {
  return Math.round(valueKmh / KMH_PER_MPH);
}

function windFromDisplay(valueMph: number): number {
  return valueMph * KMH_PER_MPH;
}

function rainForDisplay(valueMm: number): number {
  return valueMm / MM_PER_INCH;
}

function rainFromDisplay(valueInches: number): number {
  return valueInches * MM_PER_INCH;
}

function dewSpreadForDisplay(valueC: number): number {
  return Math.round(valueC * 18) / 10;
}

function dewSpreadFromDisplay(valueF: number): number {
  return (valueF * 5) / 9;
}

function selectedCloudModels(rules: ImagingRules): CloudModel[] {
  return CLOUD_MODELS.filter(({ field }) => rules[field]).map(({ key }) => key);
}

function validate(rules: ImagingRules): Partial<Record<ValidationKey, string>> {
  const errors: Partial<Record<ValidationKey, string>> = {};
  const bounded = (field: NumericField, min: number, max?: number) => {
    const value = rules[field];
    if (typeof value !== "number" || !Number.isFinite(value)) errors[field] = "Enter a number";
    else if (value < min) errors[field] = `Must be at least ${min}`;
    else if (max != null && value > max) errors[field] = `Must be at most ${max}`;
  };
  bounded("min_clear_fraction_pct", 1, 100);
  bounded("min_clear_hours", 0);
  if (rules.max_cloudy_gap_hours != null) bounded("max_cloudy_gap_hours", Number.MIN_VALUE);
  bounded("short_session_hours", Number.MIN_VALUE, 24);
  bounded("cloud_max_pct", 0, 100);
  bounded("gear_out_before_sunset_min", 0, 240);
  bounded("gear_out_after_sunrise_min", 0, 240);
  if (!Number.isInteger(rules.gear_out_before_sunset_min)) {
    errors.gear_out_before_sunset_min = "Enter a whole number";
  }
  if (!Number.isInteger(rules.gear_out_after_sunrise_min)) {
    errors.gear_out_after_sunrise_min = "Enter a whole number";
  }
  bounded("rain_max_probability_pct", 0, 100);
  bounded("rain_amount_threshold_mm", 0);
  bounded("wind_max_kmh", Number.MIN_VALUE);
  bounded("gust_max_kmh", Number.MIN_VALUE);
  bounded("dew_min_spread_c", 0);
  const selected = selectedCloudModels(rules);
  if (selected.length === 0) errors.cloud_models = "Choose at least one cloud forecast";
  else if (!selected.includes(rules.cloud_preferred_model)) {
    errors.cloud_preferred_model =
      "The preferred cloud forecast must be one of the ticked forecasts";
  }
  return errors;
}

function NumberField({
  label,
  note,
  field,
  rules,
  setRules,
  error,
  min,
  max,
  step = 1,
  disabled = false,
  toDisplay = (value) => value,
  fromDisplay = (value) => value,
}: {
  label: string;
  note: string;
  field: NumericField;
  rules: ImagingRules;
  setRules: (rules: ImagingRules) => void;
  error?: string;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  toDisplay?: (value: number) => number;
  fromDisplay?: (value: number) => number;
}) {
  const raw = rules[field];
  const displayed = typeof raw === "number" && Number.isFinite(raw) ? toDisplay(raw) : "";
  return (
    <NoteTooltip note={note}>
      <TextField
        label={label}
        type="number"
        size="small"
        value={displayed}
        disabled={disabled}
        error={Boolean(error)}
        helperText={error}
        onChange={(event) => {
          const value =
            event.target.value === "" ? Number.NaN : fromDisplay(Number(event.target.value));
          setRules({ ...rules, [field]: value });
        }}
        slotProps={{
          inputLabel: { shrink: true },
          htmlInput: {
            min: min == null ? undefined : toDisplay(min),
            max: max == null ? undefined : toDisplay(max),
            step,
          },
        }}
        fullWidth
        sx={{ minWidth: 120, flex: 1 }}
      />
    </NoteTooltip>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {title}
      </Typography>
      <Stack spacing={1.5}>{children}</Stack>
    </Box>
  );
}

export default function RulesEditor({
  locationId,
  locationName,
  saved,
  rules,
  units,
  presets,
  otherLocations,
  onDraftChange,
  onCancel,
  onSaved,
  previewCounts,
  updating,
}: {
  locationId: number;
  locationName: string;
  saved: boolean;
  rules: ImagingRules;
  units: WeatherUnits;
  presets: ImagingRulesPreset[];
  otherLocations: Location[];
  onDraftChange: (rules: ImagingRules | null) => void;
  onCancel: () => void;
  onSaved: () => void;
  previewCounts: PreviewCounts;
  updating: boolean;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<ImagingRules>(() => structuredClone(rules));
  const [copyFrom, setCopyFrom] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const activeLocation = useRef(locationId);
  useEffect(() => {
    activeLocation.current = locationId;
    return () => {
      activeLocation.current = -1;
    };
  }, [locationId]);
  const errors = useMemo(() => validate(draft), [draft]);
  const valid = Object.keys(errors).length === 0;
  const hasError = (fields: NumericField[]) => fields.some((field) => errors[field]);
  const allNight = draft.session_style === "all_night";
  const nightOff = draft.rain_policy === "night_off";
  const selectedModels = selectedCloudModels(draft);

  useEffect(() => {
    if (!valid) return;
    const timer = window.setTimeout(() => onDraftChange(structuredClone(draft)), 300);
    return () => window.clearTimeout(timer);
  }, [draft, onDraftChange, valid]);

  const handleCopy = async (value: string) => {
    setCopyFrom(value);
    if (!value) return;
    const requestLocation = locationId;
    try {
      const response = await fetchImagingRules(Number(value));
      if (activeLocation.current !== requestLocation) return;
      setDraft(structuredClone(response.rules));
    } catch (error) {
      if (activeLocation.current === requestLocation) {
        setSaveError(error instanceof Error ? error.message : "Could not copy rules");
      }
    }
  };

  const handleSave = async () => {
    if (!valid) return;
    setSaving(true);
    setSaveError(null);
    try {
      const response = await saveImagingRules(locationId, draft);
      queryClient.setQueryData(["imaging-rules", locationId], response);
      await queryClient.invalidateQueries({ queryKey: ["weather-forecast", locationId] });
      setSaving(false);
      onDraftChange(null);
      onSaved();
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Could not save rules");
      setSaving(false);
    }
  };

  const toggleCloudModel = (model: (typeof CLOUD_MODELS)[number], checked: boolean) => {
    if (!checked && selectedModels.length === 1) return;
    const next = { ...draft, [model.field]: checked };
    const nextSelected = selectedCloudModels(next);
    if (!nextSelected.includes(next.cloud_preferred_model)) {
      next.cloud_preferred_model = nextSelected[0];
    }
    setDraft(next);
  };

  const cancel = () => {
    onDraftChange(null);
    onCancel();
  };

  return (
    <Paper
      variant="outlined"
      sx={{ borderColor: "primary.main", borderWidth: 2, p: 2, mb: 2 }}
    >
      <Stack direction="row" gap={1} alignItems="center" sx={{ mb: 1.5 }}>
        <Typography variant="h6">Imaging rules for {locationName}</Typography>
        <Stack direction="row" gap={1} sx={{ ml: "auto" }}>
          <Button disabled={saving} onClick={cancel}>Cancel</Button>
          <Button variant="contained" disabled={!valid || saving} onClick={handleSave}>
            {saving ? "Saving…" : `Save for ${locationName}`}
          </Button>
        </Stack>
      </Stack>

      <Stack
        direction={{ xs: "column", md: "row" }}
        gap={1}
        alignItems={{ md: "center" }}
        sx={{ mb: 2 }}
      >
        {!saved && (
          <>
            <Typography variant="body2" color="text.secondary">
              <LabelNote
                label="Start with a preset:"
                note="Fill in starting values, then adjust and save your rules."
              />
            </Typography>
            {presets.map((preset) => {
              const notes = {
                left_out_all_night:
                  "Load all-night rules: 10% chance limit, all listed precipitation amount forecasts, whole night off, and wind limits.",
                attended_session:
                  "Load a short session: 20% chance limit, main forecast amounts, affected hours lost, and wind limits.",
                dome:
                  "Load all-night rules: 20% chance limit, main forecast amounts, affected hours lost, and wind ignored.",
              };
              return (
                <NoteTooltip key={preset.key} note={notes[preset.key]}>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => setDraft(structuredClone(preset.rules))}
                  >
                    {preset.label}
                  </Button>
                </NoteTooltip>
              );
            })}
          </>
        )}
        {otherLocations.length > 0 && (
          <NoteTooltip
            note="Replace unsaved rules with those from another location. Review and save to apply."
          >
            <FormControl
              size="small"
              sx={{ minWidth: 260, ml: { md: saved ? 0 : "auto" } }}
            >
              <FormLabel>
                <LabelNote
                  label="Copy rules from another location"
                  note="Replace unsaved rules with those from another location. Review and save to apply."
                />
              </FormLabel>
              <Select
                displayEmpty
                value={copyFrom}
                onChange={(event) => void handleCopy(event.target.value)}
                inputProps={{ "aria-label": "Copy rules from another location" }}
              >
                <MenuItem value="">Copy rules from another location</MenuItem>
                {otherLocations.map((location) => (
                  <MenuItem key={location.id} value={String(location.id)}>
                    {location.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </NoteTooltip>
        )}
      </Stack>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            md: "repeat(2, minmax(0, 1fr))",
            xl: "repeat(4, minmax(0, 1fr))",
          },
          gap: 2.5,
        }}
      >
        <Section title="How you image">
          <NoteTooltip note="Choose how far below the horizon the Sun must be before imaging time counts. This setting does not account for moonlight.">
            <FormControl size="small">
              <FormLabel>
                <LabelNote
                  label="Required darkness"
                  note="Choose how far below the horizon the Sun must be before imaging time counts. This setting does not account for moonlight."
                />
              </FormLabel>
              <Select
                value={draft.darkness}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    darkness: event.target.value as ImagingRules["darkness"],
                  })
                }
              >
                <MenuItem value="astronomical">
                  Astronomical (Sun 18° below horizon)
                </MenuItem>
                <MenuItem value="nautical">Nautical (Sun 12° below horizon)</MenuItem>
                <MenuItem value="civil">Civil (Sun 6° below horizon)</MenuItem>
              </Select>
            </FormControl>
          </NoteTooltip>
          <FormControl>
            <FormLabel>
              <LabelNote
                label="Session"
                note="Choose enough total usable time across the night or one uninterrupted stretch."
              />
            </FormLabel>
            <RadioGroup
              row
              value={draft.session_style}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  session_style: event.target.value as ImagingRules["session_style"],
                })
              }
            >
              <NoteTooltip note="Add up usable time across your selected dark hours. Both the percentage and minimum hours must be reached.">
                <FormControlLabel
                  value="all_night"
                  control={<Radio size="small" />}
                  label="All night"
                />
              </NoteTooltip>
              <NoteTooltip note="Require one uninterrupted usable stretch lasting at least your chosen number of hours.">
                <FormControlLabel
                  value="short_session"
                  control={<Radio size="small" />}
                  label="Short session"
                />
              </NoteTooltip>
            </RadioGroup>
            <Typography variant="caption" color="text.secondary">
              Usable time meets your enabled hourly limits.
            </Typography>
          </FormControl>
          {allNight ? (
            <>
              <NumberField
                label="Minimum usable time (% of dark time)"
                note="Minimum share of selected dark time that must be usable. For example, 50% of six dark hours is three hours."
                field="min_clear_fraction_pct"
                rules={draft}
                setRules={setDraft}
                error={errors.min_clear_fraction_pct}
                min={1}
                max={100}
              />
              <NumberField
                label="Minimum usable time (hours)"
                note="Minimum total usable time, even when the percentage would allow less. Both requirements must be met."
                field="min_clear_hours"
                rules={draft}
                setRules={setDraft}
                error={errors.min_clear_hours}
                min={0}
                step={0.5}
              />
              <NoteTooltip note="Longest stretch without usable imaging time, including at the start or end. Leave blank for no limit.">
                <TextField
                  label="Longest interruption (hours)"
                  type="number"
                  size="small"
                  fullWidth
                  value={draft.max_cloudy_gap_hours ?? ""}
                  placeholder="No limit"
                  error={Boolean(errors.max_cloudy_gap_hours)}
                  helperText={errors.max_cloudy_gap_hours}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      max_cloudy_gap_hours:
                        event.target.value === "" ? null : Number(event.target.value),
                    })
                  }
                  slotProps={{
                    inputLabel: { shrink: true },
                    htmlInput: { min: 0.1, step: 0.5 },
                  }}
                />
              </NoteTooltip>
              {hasError(["short_session_hours"]) && (
                <Typography variant="caption" color="error">
                  The short-session setting has an invalid value. Switch to Short
                  session to fix it.
                </Typography>
              )}
            </>
          ) : (
            <>
              <NumberField
                label="Minimum usable hours in a row"
                note="Required length of one uninterrupted usable stretch. Separate shorter stretches do not add together."
                field="short_session_hours"
                rules={draft}
                setRules={setDraft}
                error={errors.short_session_hours}
                min={0.1}
                max={24}
                step={0.5}
              />
              {hasError([
                "min_clear_fraction_pct",
                "min_clear_hours",
                "max_cloudy_gap_hours",
              ]) && (
                <Typography variant="caption" color="error">
                  An all-night setting has an invalid value. Switch to All night to
                  fix it.
                </Typography>
              )}
            </>
          )}
        </Section>

        <Section title="Cloud">
          <NumberField
            label="Maximum cloud cover (%)"
            note="Maximum total cloud cover allowed by each forecast’s cloud check. Exactly at the limit passes."
            field="cloud_max_pct"
            rules={draft}
            setRules={setDraft}
            error={errors.cloud_max_pct}
            min={0}
            max={100}
          />
          <FormControl error={Boolean(errors.cloud_models)}>
            <FormLabel>
              <LabelNote
                label="Cloud forecasts"
                note="Choose at least one cloud forecast. Unticked forecasts remain visible in night details but do not decide the cloud check."
              />
            </FormLabel>
            <Box sx={{ display: "flex", flexWrap: "wrap" }}>
              {CLOUD_MODELS.map((model) => (
                <NoteTooltip key={model.key} note={model.note}>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={draft[model.field]}
                        disabled={draft[model.field] && selectedModels.length === 1}
                        onChange={(event) => toggleCloudModel(model, event.target.checked)}
                      />
                    }
                    label={model.label}
                  />
                </NoteTooltip>
              ))}
            </Box>
            {errors.cloud_models && (
              <Typography variant="caption" color="error">
                {errors.cloud_models}
              </Typography>
            )}
          </FormControl>
          {selectedModels.length > 1 && (
            <>
              <NoteTooltip note="Break ties with this forecast; if it cannot reach an hour, use the first selected forecast that can: ECMWF, GFS, then ICON.">
                <FormControl size="small" error={Boolean(errors.cloud_preferred_model)}>
                  <FormLabel>
                    <LabelNote
                      label="Preferred cloud forecast"
                      note="Break ties with this forecast; if it cannot reach an hour, use the first selected forecast that can: ECMWF, GFS, then ICON."
                    />
                  </FormLabel>
                  <Select
                    value={draft.cloud_preferred_model}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        cloud_preferred_model: event.target.value as CloudModel,
                      })
                    }
                  >
                    {CLOUD_MODELS.filter(({ key }) => selectedModels.includes(key)).map(
                      (model) => (
                        <MenuItem key={model.key} value={model.key}>{model.label}</MenuItem>
                      ),
                    )}
                  </Select>
                  {errors.cloud_preferred_model && (
                    <Typography variant="caption" color="error">
                      {errors.cloud_preferred_model}
                    </Typography>
                  )}
                </FormControl>
              </NoteTooltip>
              <FormControl>
                <FormLabel>
                  <LabelNote
                    label="When forecasts differ"
                    note="Choose how selected cloud forecasts affect the verdict when they disagree."
                  />
                </FormLabel>
                <RadioGroup
                  value={draft.cloud_combination}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      cloud_combination: event.target.value as ImagingRules["cloud_combination"],
                    })
                  }
                >
                  <NoteTooltip note="Follow most selected forecasts that reach each hour. Ties use your preferred forecast when it reaches that hour.">
                    <FormControlLabel
                      value="majority"
                      control={<Radio size="small" />}
                      label="Majority for each hour"
                    />
                  </NoteTooltip>
                  <NoteTooltip note="Keep each forecast’s session result. Conflicting results, or different usable stretches for a short session, can produce Uncertain.">
                    <FormControlLabel
                      value="uncertain"
                      control={<Radio size="small" />}
                      label="Show Uncertain"
                    />
                  </NoteTooltip>
                </RadioGroup>
              </FormControl>
            </>
          )}
        </Section>

        <Section title="Precipitation">
          <NumberField
            label="Maximum precipitation chance (%)"
            note="An hour fails if its forecast chance is above this. In North America, beyond about 36 hours, one chance covers each 6-hour stretch and repeats in each hour."
            field="rain_max_probability_pct"
            rules={draft}
            setRules={setDraft}
            error={errors.rain_max_probability_pct}
            min={0}
            max={100}
          />
          <Typography variant="caption" color="text.secondary">
            A 0% limit fails any hour with even a 1% chance.
          </Typography>
          <NumberField
            label={`Maximum precipitation amount (${units === "imperial" ? "in/h" : "mm/h"})`}
            note="An amount above this limit fails; an equal amount passes. Set to zero to reject any positive amount."
            field="rain_amount_threshold_mm"
            rules={draft}
            setRules={setDraft}
            error={errors.rain_amount_threshold_mm}
            min={0}
            step={units === "imperial" ? 0.01 : 0.1}
            toDisplay={units === "imperial" ? rainForDisplay : undefined}
            fromDisplay={units === "imperial" ? rainFromDisplay : undefined}
          />
          <FormControl>
            <FormLabel>
              <LabelNote
                label="Precipitation amount forecasts"
                note="Choose which forecasts supply amounts to check. Precipitation chance always comes from the main forecast."
              />
            </FormLabel>
            <RadioGroup
              value={draft.rain_forecasts}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  rain_forecasts: event.target.value as ImagingRules["rain_forecasts"],
                })
              }
            >
              <NoteTooltip note="Check precipitation amounts from Open-Meteo’s standard forecast for this location.">
                <FormControlLabel
                  value="main"
                  control={<Radio size="small" />}
                  label="Main forecast"
                />
              </NoteTooltip>
              <NoteTooltip note="Also check ECMWF, GFS and ICON amounts within their reach. Cloud forecast selections do not change this choice.">
                <FormControlLabel
                  value="any_model"
                  control={<Radio size="small" />}
                  label="Main forecast + ECMWF, GFS and ICON"
                />
              </NoteTooltip>
            </RadioGroup>
          </FormControl>
          <FormControl>
            <FormLabel>
              <LabelNote
                label="When a precipitation limit is exceeded"
                note="Choose whether exceeding the chance or amount limit rules out the whole night or only the affected imaging hours."
              />
            </FormLabel>
            <RadioGroup
              value={draft.rain_policy}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  rain_policy: event.target.value as ImagingRules["rain_policy"],
                })
              }
            >
              <NoteTooltip note="Exceeding either precipitation limit while your gear is out makes the night No, even outside imaging hours.">
                <FormControlLabel
                  value="night_off"
                  control={<Radio size="small" />}
                  label="The whole night is off"
                />
              </NoteTooltip>
              <NoteTooltip note="Remove imaging hours that exceed either precipitation limit. The remaining time can still meet your session requirements.">
                <FormControlLabel
                  value="hours_lost"
                  control={<Radio size="small" />}
                  label="Only those hours are lost"
                />
              </NoteTooltip>
            </RadioGroup>
          </FormControl>
          {nightOff ? (
            <Stack spacing={1.5}>
              <NumberField
                label="Default gear-out time (min before sunset)"
                note="How early your gear is out before sunset. Precipitation checks start here. You can change this time for an individual night."
                field="gear_out_before_sunset_min"
                rules={draft}
                setRules={setDraft}
                error={errors.gear_out_before_sunset_min}
                min={0}
                max={240}
              />
              <NumberField
                label="Default gear-in time (min after sunrise)"
                note="How long your gear stays out after sunrise. This sets the planned end of precipitation checks. Individual nights can use another time."
                field="gear_out_after_sunrise_min"
                rules={draft}
                setRules={setDraft}
                error={errors.gear_out_after_sunrise_min}
                min={0}
                max={240}
              />
            </Stack>
          ) : (
            hasError(["gear_out_before_sunset_min", "gear_out_after_sunrise_min"]) && (
              <Typography variant="caption" color="error">
                A gear-out time has an invalid value. Choose “The whole night is off”
                to fix it.
              </Typography>
            )
          )}
        </Section>

        <Section title="Optional limits">
          <NoteTooltip note="Apply steady-wind and gust limits to imaging hours. When off, wind remains visible in night details.">
            <FormControlLabel
              control={
                <Checkbox
                  checked={draft.wind_counted}
                  onChange={(event) =>
                    setDraft({ ...draft, wind_counted: event.target.checked })
                  }
                />
              }
              label="Use wind limits"
            />
          </NoteTooltip>
          <Stack spacing={1.5} sx={{ opacity: draft.wind_counted ? 1 : 0.45 }}>
            <NumberField
              label={`Maximum steady wind (${units === "imperial" ? "mph" : "km/h"})`}
              note="Hours with steady wind above this value are unusable. Exactly at the limit passes."
              field="wind_max_kmh"
              rules={draft}
              setRules={setDraft}
              error={errors.wind_max_kmh}
              min={0.1}
              disabled={!draft.wind_counted}
              toDisplay={units === "imperial" ? windForDisplay : undefined}
              fromDisplay={units === "imperial" ? windFromDisplay : undefined}
            />
            <NumberField
              label={`Maximum gust speed (${units === "imperial" ? "mph" : "km/h"})`}
              note="Hours with gusts above this value are unusable, even if steady wind is below its limit."
              field="gust_max_kmh"
              rules={draft}
              setRules={setDraft}
              error={errors.gust_max_kmh}
              min={0.1}
              disabled={!draft.wind_counted}
              toDisplay={units === "imperial" ? windForDisplay : undefined}
              fromDisplay={units === "imperial" ? windFromDisplay : undefined}
            />
          </Stack>
          <NoteTooltip note="Exclude hours when air temperature is too close to the dew point, using the minimum difference below.">
            <FormControlLabel
              control={
                <Checkbox
                  checked={draft.dew_counted}
                  onChange={(event) =>
                    setDraft({ ...draft, dew_counted: event.target.checked })
                  }
                />
              }
              label="Use dew limit"
            />
          </NoteTooltip>
          <Box sx={{ opacity: draft.dew_counted ? 1 : 0.45 }}>
            <NumberField
              label={`Minimum temperature above dew point (°${units === "imperial" ? "F" : "C"})`}
              note="Required difference between air temperature and dew point. A 3°C / 5.4°F setting excludes hours with a smaller difference."
              field="dew_min_spread_c"
              rules={draft}
              setRules={setDraft}
              error={errors.dew_min_spread_c}
              min={0}
              step={units === "imperial" ? 0.1 : 0.5}
              disabled={!draft.dew_counted}
              toDisplay={units === "imperial" ? dewSpreadForDisplay : undefined}
              fromDisplay={units === "imperial" ? dewSpreadFromDisplay : undefined}
            />
          </Box>
          <NoteTooltip note="Only count hours with the Moon below the horizon, regardless of its phase or your filter.">
            <FormControlLabel
              control={
                <Checkbox
                  checked={draft.moon_must_be_down}
                  onChange={(event) =>
                    setDraft({ ...draft, moon_must_be_down: event.target.checked })
                  }
                />
              }
              label="Require Moon below horizon"
            />
          </NoteTooltip>
        </Section>
      </Box>

      {saveError && <Alert severity="warning" sx={{ mt: 1.5 }}>{saveError}</Alert>}
      <Box
        sx={{
          display: "flex",
          flexWrap: "wrap",
          gap: 1,
          mt: 2,
          pt: 1.5,
          borderTop: 1,
          borderColor: "divider",
        }}
      >
        <Typography variant="body2">
          This week with these rules: <b>{previewCounts.go} Go</b> ·{" "}
          <b>{previewCounts.uncertain} Uncertain</b> · <b>{previewCounts.no} No</b> ·{" "}
          <b>{previewCounts.notEnough} Not enough data</b>
        </Typography>
        {updating && <Typography variant="caption" color="text.secondary">Updating…</Typography>}
      </Box>
    </Paper>
  );
}
