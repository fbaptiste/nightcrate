import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Slider from "@mui/material/Slider";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import type { RigCalculators } from "@/api/rigs";
import { useDebounce } from "@/lib/useDebounce";
import { RIG_BLUE, RIG_ORANGE, RIG_TEAL } from "@/lib/rigColors";
import SamplingChart from "./SamplingChart";
import SubExposurePanel from "./SubExposurePanel";

interface ImagingTabProps {
  calculators: RigCalculators;
  kFactor: number;
  onKFactorChange: (k: number) => void;
  imageBinning: number;
  onImageBinningChange: (b: number) => void;
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
  seeingValue: number,
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

export default function ImagingTab({
  calculators,
  kFactor,
  onKFactorChange,
  imageBinning,
  onImageBinningChange,
}: ImagingTabProps) {
  const initialSeeingMid =
    (calculators.sampling_assessment.seeing_fwhm_low +
      calculators.sampling_assessment.seeing_fwhm_high) /
    2;
  const [seeingSlider, setSeeingSlider] = useState<number>(
    initialSeeingMid > 0 ? initialSeeingMid : 3.0,
  );

  const debouncedSeeing = useDebounce(seeingSlider, 100);

  const sampling = useMemo(() => {
    return assessSampling(
      calculators.image_scale_arcsec_per_pixel,
      debouncedSeeing,
    );
  }, [calculators.image_scale_arcsec_per_pixel, debouncedSeeing]);

  const scale = calculators.image_scale_arcsec_per_pixel;
  const binnedScale = scale * imageBinning;
  const [fovW, fovH] = calculators.field_of_view_arcmin;
  const [degW, degH] = calculators.field_of_view_deg;

  return (
    <Box>
      {/* Binning selector */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="body2" gutterBottom>
          Binning
        </Typography>
        <ToggleButtonGroup
          value={imageBinning}
          exclusive
          onChange={(_, val) => {
            if (val !== null) onImageBinningChange(val);
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
            value={`${fovW.toFixed(1)}\u2032 \u00d7 ${fovH.toFixed(1)}\u2032 (${degW.toFixed(2)}\u00b0 \u00d7 ${degH.toFixed(2)}\u00b0)`}
          />
          <MetricRow
            label="Focal Ratio"
            value={`f/${calculators.focal_ratio}`}
          />
          <MetricRow
            label="Dawes Limit"
            value={`${calculators.dawes_limit_arcsec.toFixed(2)}\u2033`}
          />
          <MetricRow
            label="Rayleigh Limit"
            value={`${calculators.rayleigh_limit_arcsec.toFixed(2)}\u2033`}
          />
          {calculators.sensor_coverage_pct != null && (
            <MetricRow
              label="Sensor Coverage"
              value={`${calculators.sensor_coverage_pct.toFixed(0)}% of image circle`}
              warning={calculators.sensor_coverage_pct > 100}
            />
          )}
        </tbody>
      </Box>

      {/* Sampling assessment */}
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
        Sampling Assessment
      </Typography>

      <Box
        sx={{
          display: "flex",
          gap: 3,
          alignItems: "flex-start",
          flexWrap: "wrap",
        }}
      >
        <Box>
          <Typography variant="body2" gutterBottom>
            Seeing: {seeingSlider.toFixed(1)}&Prime;
          </Typography>
          <Slider
            value={seeingSlider}
            min={0.5}
            max={6.0}
            step={0.1}
            onChange={(_, v) => setSeeingSlider(v as number)}
            valueLabelDisplay="auto"
            valueLabelFormat={(v) => `${v.toFixed(1)}\u2033`}
            sx={{ maxWidth: 350 }}
          />
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              maxWidth: 350,
              mb: 1.5,
            }}
          >
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

        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "200px 200px",
            gap: 2,
            fontSize: "0.75rem",
            color: "text.secondary",
          }}
        >
          <Typography variant="caption" component="p">
            Sampling describes how your pixel scale relates to atmospheric seeing.
            Each bar shows the effective pixel scale at that binning level. The
            shaded region marks the ideal sampling zone for the selected seeing
            conditions.
          </Typography>
          <Box>
            <Typography variant="caption" component="p" sx={{ mb: 0.5 }}>
              <Box component="span" sx={{ color: RIG_BLUE, fontWeight: 600 }}>
                Blue bars
              </Box>{" "}
              fall within the ideal range (well-sampled) — stars span 2–3 pixels,
              balancing resolution and signal.
            </Typography>
            <Typography variant="caption" component="p" sx={{ mb: 0.5 }}>
              <Box component="span" sx={{ color: RIG_ORANGE, fontWeight: 600 }}>
                Orange bars
              </Box>{" "}
              are oversampled — pixel scale is finer than the seeing supports,
              wasting signal-to-noise. Consider binning.
            </Typography>
            <Typography variant="caption" component="p">
              <Box component="span" sx={{ color: RIG_TEAL, fontWeight: 600 }}>
                Teal bars
              </Box>{" "}
              are undersampled — pixel scale is too coarse, stars look blocky.
              Consider a longer focal length or smaller pixels.
            </Typography>
          </Box>
        </Box>
      </Box>

      <SubExposurePanel
        subExposure={calculators.sub_exposure}
        kFactor={kFactor}
        onKFactorChange={onKFactorChange}
      />
    </Box>
  );
}

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
            <WarningAmberIcon sx={{ fontSize: 16, color: "warning.main" }} />
          )}
        </Box>
      </td>
    </tr>
  );
}
