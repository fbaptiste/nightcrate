import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Slider from "@mui/material/Slider";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { fetchLocations, type Location } from "@/api/locations";
import {
  fetchRigCalculators,
  type Rig,
  type RigCalculators,
} from "@/api/rigs";
import { useDebounce } from "@/lib/useDebounce";
import { RIG_BLUE, RIG_ORANGE, RIG_TEAL } from "@/lib/rigColors";
import SamplingChart from "./SamplingChart";
import GuideSuitabilityPanel from "./GuideSuitabilityPanel";

interface CalculatorPanelProps {
  rig: Rig;
}

const SEEING_LABELS: { range: [number, number]; label: string }[] = [
  { range: [0.5, 1.0], label: "Excellent" },
  { range: [1.0, 2.0], label: "Good" },
  { range: [2.0, 4.0], label: "OK" },
  { range: [4.0, 5.0], label: "Poor" },
  { range: [5.0, 6.0], label: "Very Poor" },
];

function assessSampling(
  imageScale: number,
  seeingValue: number
): {
  idealLow: number;
  idealHigh: number;
  binningRecommendations: Record<number, string>;
} {
  const idealLow = seeingValue / 3.0;
  const idealHigh = seeingValue / 2.0;
  const assess = (scale: number) => {
    if (scale < idealLow) return "oversampled";
    if (scale > idealHigh) return "undersampled";
    return "well_sampled";
  };
  const binningRecommendations: Record<number, string> = {};
  for (let bin = 1; bin <= 4; bin++) {
    binningRecommendations[bin] = assess(imageScale * bin);
  }
  return { idealLow, idealHigh, binningRecommendations };
}

export default function CalculatorPanel({ rig }: CalculatorPanelProps) {
  const [selectedLocationId, setSelectedLocationId] = useState<number | null>(
    null
  );
  const [seeingSlider, setSeeingSlider] = useState<number | null>(null);
  const [binning, setBinning] = useState<number>(1);
  const [guideBinning, setGuideBinning] = useState<number>(1);
  const [centroidAccuracy, setCentroidAccuracy] = useState<number>(0.2);
  const [calculatorData, setCalculatorData] = useState<RigCalculators>(
    rig.calculators
  );

  const debouncedGuideBinning = useDebounce(guideBinning, 150);
  const debouncedCentroidAccuracy = useDebounce(centroidAccuracy, 300);

  const { data: locations = [] } = useQuery<Location[]>({
    queryKey: ["locations"],
    queryFn: fetchLocations,
  });

  // Set default location on first load
  useEffect(() => {
    if (locations.length > 0 && selectedLocationId === null) {
      const defaultLoc = locations.find((l) => l.is_default);
      if (defaultLoc) {
        setSelectedLocationId(defaultLoc.id);
      }
    }
  }, [locations, selectedLocationId]);

  // Fetch calculator data when location or guide params change.
  useEffect(() => {
    if (selectedLocationId === null) return;
    let cancelled = false;
    fetchRigCalculators(rig.id, {
      location_id: selectedLocationId,
      guide_binning: debouncedGuideBinning,
      centroid_accuracy_pixels: debouncedCentroidAccuracy,
    }).then((data) => {
      if (!cancelled) {
        setCalculatorData(data);
        // Only reset the seeing slider when the location itself changed,
        // not on every guide-param refetch.
        setSeeingSlider((prev) => {
          if (prev !== null) return prev;
          const mid =
            (data.sampling_assessment.seeing_fwhm_low +
              data.sampling_assessment.seeing_fwhm_high) /
            2;
          return mid > 0 ? mid : null;
        });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [
    rig.id,
    selectedLocationId,
    debouncedGuideBinning,
    debouncedCentroidAccuracy,
  ]);

  // Reset seeing slider when location changes (separate effect so guide-param
  // refetches don't reset the slider mid-session).
  useEffect(() => {
    setSeeingSlider(null);
  }, [selectedLocationId]);

  const selectedLocation = locations.find((l) => l.id === selectedLocationId);
  const hasSeeing =
    selectedLocation?.typical_seeing_low_arcsec != null &&
    selectedLocation?.typical_seeing_high_arcsec != null;

  // Seeing value for computation
  const seeingValue = seeingSlider ?? 3.0;
  const debouncedSeeing = useDebounce(seeingValue, 100);

  // Compute sampling assessment client-side based on slider
  const sampling = useMemo(() => {
    const scale = calculatorData.image_scale_arcsec_per_pixel;
    return assessSampling(scale, debouncedSeeing);
  }, [calculatorData.image_scale_arcsec_per_pixel, debouncedSeeing]);

  // Derived values with binning applied
  const scale = calculatorData.image_scale_arcsec_per_pixel;
  const binnedScale = scale * binning;
  const [fovW, fovH] = calculatorData.field_of_view_arcmin;
  const [degW, degH] = calculatorData.field_of_view_deg;
  const binnedFovW = fovW; // FOV doesn't change with binning, only resolution
  const binnedFovH = fovH;
  const binnedDegW = degW;
  const binnedDegH = degH;

  return (
    <Box sx={{ px: 2, pb: 2, pt: 1 }}>
      {/* Location selector */}
      <Autocomplete
        size="small"
        options={locations}
        getOptionLabel={(loc) =>
          `${loc.name}${loc.is_default ? " (default)" : ""}`
        }
        value={selectedLocation ?? null}
        onChange={(_, loc) => {
          if (loc) setSelectedLocationId(loc.id);
        }}
        renderInput={(params) => <TextField {...params} label="Location" />}
        sx={{ maxWidth: 300, mb: 1.5 }}
        isOptionEqualToValue={(option, value) => option.id === value.id}
      />

      {!hasSeeing && selectedLocation && (
        <Typography variant="caption" color="text.secondary" sx={{ mb: 1.5, display: "block" }}>
          Set typical seeing for this location in Location settings for a more
          accurate assessment.
        </Typography>
      )}

      {/* Binning selector */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="body2" gutterBottom>
          Binning
        </Typography>
        <ToggleButtonGroup
          value={binning}
          exclusive
          onChange={(_, val) => {
            if (val !== null) setBinning(val);
          }}
          size="small"
        >
          {[1, 2, 3, 4].map((b) => (
            <ToggleButton key={b} value={b}>
              {b}&times;{b}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Box>

      {/* Metrics table */}
      <Box
        component="table"
        sx={{
          "& td": { py: 0.3, pr: 2, verticalAlign: "top" },
          mb: 2,
        }}
      >
        <tbody>
          <MetricRow
            label="Image Scale"
            value={`${binnedScale.toFixed(2)}\u2033/pixel`}
          />
          <MetricRow
            label="Field of View"
            value={`${binnedFovW.toFixed(1)}\u2032 \u00d7 ${binnedFovH.toFixed(1)}\u2032 (${binnedDegW.toFixed(2)}\u00b0 \u00d7 ${binnedDegH.toFixed(2)}\u00b0)`}
          />
          <MetricRow
            label="Focal Ratio"
            value={`f/${calculatorData.focal_ratio}`}
          />
          <MetricRow
            label="Dawes Limit"
            value={`${calculatorData.dawes_limit_arcsec.toFixed(2)}\u2033`}
          />
          <MetricRow
            label="Rayleigh Limit"
            value={`${calculatorData.rayleigh_limit_arcsec.toFixed(2)}\u2033`}
          />
          {calculatorData.sensor_coverage_pct != null && (
            <MetricRow
              label="Sensor Coverage"
              value={`${calculatorData.sensor_coverage_pct.toFixed(0)}% of image circle`}
              warning={calculatorData.sensor_coverage_pct > 100}
            />
          )}
        </tbody>
      </Box>

      {/* Sampling assessment */}
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
        Sampling Assessment
      </Typography>

      <Box sx={{ display: "flex", gap: 3, alignItems: "flex-start", flexWrap: "wrap" }}>
        {/* Left column: seeing slider + chart */}
        <Box>
          <Typography variant="body2" gutterBottom>
            Seeing: {seeingValue.toFixed(1)}&Prime;
          </Typography>
          <Slider
            value={seeingValue}
            min={0.5}
            max={6.0}
            step={0.1}
            onChange={(_, v) => setSeeingSlider(v as number)}
            valueLabelDisplay="auto"
            valueLabelFormat={(v) => `${v.toFixed(1)}\u2033`}
            sx={{ maxWidth: 350 }}
          />
          <Box sx={{ display: "flex", justifyContent: "space-between", maxWidth: 350, mb: 1.5 }}>
            {SEEING_LABELS.map(({ label }) => (
              <Typography
                key={label}
                variant="caption"
                color="text.secondary"
                sx={{ fontSize: "0.65rem" }}
              >
                {label}
              </Typography>
            ))}
          </Box>
          <SamplingChart
            imageScale={scale}
            idealRangeLow={sampling.idealLow}
            idealRangeHigh={sampling.idealHigh}
            binningRecommendations={sampling.binningRecommendations}
          />
        </Box>

        {/* Right column: help text in two narrow columns */}
        <Box sx={{ display: "grid", gridTemplateColumns: "200px 200px", gap: 2, fontSize: "0.75rem", color: "text.secondary" }}>
          <Typography variant="caption" component="p">
            Sampling describes how your pixel scale relates to atmospheric seeing.
            Each bar shows the effective pixel scale at that binning level.
            The shaded region marks the ideal sampling zone for the selected seeing conditions.
          </Typography>
          <Box>
            <Typography variant="caption" component="p" sx={{ mb: 0.5 }}>
              <Box component="span" sx={{ color: RIG_BLUE, fontWeight: 600 }}>Blue bars</Box>
              {" "}fall within the ideal range (well-sampled) — stars span 2–3 pixels, balancing resolution and signal.
            </Typography>
            <Typography variant="caption" component="p" sx={{ mb: 0.5 }}>
              <Box component="span" sx={{ color: RIG_ORANGE, fontWeight: 600 }}>Orange bars</Box>
              {" "}are oversampled — pixel scale is finer than the seeing supports, wasting signal-to-noise. Consider binning.
            </Typography>
            <Typography variant="caption" component="p">
              <Box component="span" sx={{ color: RIG_TEAL, fontWeight: 600 }}>Teal bars</Box>
              {" "}are undersampled — pixel scale is too coarse, stars look blocky. Consider a longer focal length or smaller pixels.
            </Typography>
          </Box>
        </Box>
      </Box>

      {/* Guide suitability */}
      <GuideSuitabilityPanel
        rig={rig}
        suitability={calculatorData.guide_suitability}
        mainImageScale={scale}
        guideBinning={guideBinning}
        onBinningChange={setGuideBinning}
        centroidAccuracy={centroidAccuracy}
        onCentroidChange={setCentroidAccuracy}
      />
    </Box>
  );
}

const METRIC_TOOLTIPS: Record<string, string> = {
  "Image Scale":
    "Angular size each pixel covers on the sky. Smaller values mean higher resolution but require better seeing and guiding.",
  "Field of View":
    "Total sky area captured by the sensor. Determines how much of a target fits in a single frame.",
  "Focal Ratio":
    "The telescope's effective f-number. Lower f-ratios gather light faster (shorter exposures) but have a shallower depth of focus.",
  "Dawes Limit":
    "Theoretical minimum angular separation to resolve two equal-brightness stars, based on aperture. Seeing usually limits resolution before this.",
  "Rayleigh Limit":
    "Angular resolution limit where the first diffraction minimum of one star overlaps the central maximum of another. Slightly more conservative than Dawes.",
  "Sensor Coverage":
    "How much of the telescope's illuminated image circle the sensor covers. Values over 100% mean the sensor extends beyond the image circle, causing vignetting in the corners.",
};

function MetricRow({
  label,
  value,
  warning,
}: {
  label: string;
  value: string;
  warning?: boolean;
}) {
  const tooltip = METRIC_TOOLTIPS[label];
  const labelEl = (
    <Typography
      variant="body2"
      color="text.secondary"
      sx={tooltip ? { cursor: "help" } : undefined}
    >
      {label}
    </Typography>
  );
  return (
    <tr>
      <td>
        {tooltip ? (
          <Tooltip title={tooltip} arrow placement="right">
            {labelEl}
          </Tooltip>
        ) : (
          labelEl
        )}
      </td>
      <td>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Typography variant="body1">{value}</Typography>
          {warning && (
            <WarningAmberIcon
              sx={{ fontSize: 16, color: "warning.main" }}
            />
          )}
        </Box>
      </td>
    </tr>
  );
}
