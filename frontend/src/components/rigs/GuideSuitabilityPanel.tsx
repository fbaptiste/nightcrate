import { useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Slider from "@mui/material/Slider";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import type { GuideSuitability, Rig } from "@/api/rigs";
import { ratingColor, ratingLabel, ratingTextColor } from "@/lib/rigColors";
import CalculatorAboutSection from "./CalculatorAboutSection";
import GuideSuitabilityChart from "./GuideSuitabilityChart";

interface GuideSuitabilityPanelProps {
  rig: Rig;
  suitability: GuideSuitability | null;
  mainImageScale: number;
  guideBinning: number;
  onBinningChange: (b: number) => void;
  centroidAccuracy: number;
  onCentroidChange: (v: number) => void;
}

const METRIC_TOOLTIPS: Record<string, string> = {
  "Guide Focal Length":
    "Effective focal length the guide camera sees. For guide-scope mode it's the guide scope's focal length; for OAG it's the main scope's.",
  "Guide Image Scale":
    "Angular size each guide-camera pixel covers. Coarser scales are easier for the guiding software to centroid but less precise.",
  "Guide FOV":
    "Field of view of the guide camera. Needs to be large enough to reliably find guide stars.",
  "Effective Guide Precision":
    "Assumed guiding precision: the guide scale multiplied by PHD2's typical centroid accuracy (default 0.2 pixels).",
  "Main Image Scale":
    "Pixel scale of the imaging camera (for reference — this is the yardstick guide errors are measured against).",
  "Effective Error":
    "Guide error expressed in main-camera pixels. Below 1.0 px means guide errors are finer than your imaging resolution.",
  "G-Ratio": "Raw ratio of guide scale to main scale. Community rule of thumb: 5:1 or less.",
};

export default function GuideSuitabilityPanel({
  rig,
  suitability,
  mainImageScale,
  guideBinning,
  onBinningChange,
  centroidAccuracy,
  onCentroidChange,
}: GuideSuitabilityPanelProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const header = (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 0.5 }}>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        Guide System
      </Typography>
      <Box sx={{ flex: 1 }} />
      <Typography variant="caption" color="text.secondary">
        Binning
      </Typography>
      <ToggleButtonGroup
        value={guideBinning}
        exclusive
        size="small"
        onChange={(_, v) => {
          if (v !== null) onBinningChange(v);
        }}
      >
        {[1, 2, 3, 4].map((b) => (
          <ToggleButton key={b} value={b} sx={{ px: 1.5, py: 0.25 }}>
            {b}&times;{b}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
    </Box>
  );

  // Empty-state paths: no guide camera at all, or assigned without a path,
  // or guide scope missing focal length.
  if (suitability === null) {
    if (!rig.guide_camera_id) {
      // Don't render anything.
      return null;
    }
    const hasPath = rig.guide_scope_id != null || rig.oag_id != null;
    const message = !hasPath
      ? "Assign a guide scope or OAG to compute guide suitability."
      : `Guide scope "${rig.guide_scope_name ?? "?"}" is missing a focal length. Edit the equipment record to add one.`;
    return (
      <Box sx={{ mt: 2 }}>
        {header}
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ fontStyle: "italic", display: "block" }}
        >
          {message}
        </Typography>
      </Box>
    );
  }

  const modeLabel =
    suitability.mode === "guide_scope"
      ? `Guide-scope: ${rig.guide_scope_name ?? "?"} + ${rig.guide_camera_name ?? "?"}`
      : `OAG: ${rig.oag_name ?? "?"} + ${rig.guide_camera_name ?? "?"} (sharing main scope optics)`;

  const gRatioDisplay = `1 : ${suitability.g_ratio.toFixed(1)}`;

  const guideScaleText = suitability.guide_binning > 1
    ? `${suitability.guide_scale_arcsec_per_pixel.toFixed(2)}\u2033/pixel (unbinned: ${suitability.unbinned_guide_scale_arcsec_per_pixel.toFixed(2)}\u2033/px)`
    : `${suitability.guide_scale_arcsec_per_pixel.toFixed(2)}\u2033/pixel`;

  const focalLengthSuffix = suitability.mode === "oag" ? " (from main scope)" : "";

  return (
    <Box sx={{ mt: 2 }}>
      {header}

      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
        {modeLabel}
      </Typography>

      {/* Metrics table */}
      <Box
        component="table"
        sx={{
          "& td": { py: 0.3, pr: 2, verticalAlign: "top" },
          mb: 1.5,
        }}
      >
        <tbody>
          <MetricRow
            label="Guide Focal Length"
            value={`${suitability.guide_focal_length_mm.toFixed(0)}mm${focalLengthSuffix}`}
            tooltips={METRIC_TOOLTIPS}
          />
          <MetricRow
            label="Guide Image Scale"
            value={guideScaleText}
            tooltips={METRIC_TOOLTIPS}
          />
          <MetricRow
            label="Guide FOV"
            value={`${suitability.guide_fov_width_arcmin.toFixed(1)}\u2032 \u00d7 ${suitability.guide_fov_height_arcmin.toFixed(1)}\u2032`}
            tooltips={METRIC_TOOLTIPS}
          />
          <MetricRow
            label="Effective Guide Precision"
            value={`${suitability.effective_guide_precision_arcsec.toFixed(2)}\u2033`}
            subvalue={`@ ${suitability.centroid_accuracy_pixels.toFixed(2)} px centroid, ${suitability.guide_binning}\u00d7${suitability.guide_binning} binning`}
            tooltips={METRIC_TOOLTIPS}
          />
          <MetricRow
            label="Main Image Scale"
            value={`${mainImageScale.toFixed(2)}\u2033/pixel`}
            tooltips={METRIC_TOOLTIPS}
          />
          <MetricRow
            label="Effective Error"
            value={`${suitability.effective_error_main_pixels.toFixed(2)} main pixels`}
            tooltips={METRIC_TOOLTIPS}
          />
          <MetricRow
            label="G-Ratio"
            value={gRatioDisplay}
            tooltips={METRIC_TOOLTIPS}
          />
        </tbody>
      </Box>

      {/* Rating chip + recommendation + caveat */}
      <Box sx={{ mb: 1 }}>
        <Chip
          label={ratingLabel(suitability.rating)}
          sx={{
            bgcolor: ratingColor(suitability.rating),
            color: ratingTextColor(suitability.rating),
            fontWeight: 600,
            mb: 1,
          }}
        />
        <Typography variant="body2" sx={{ mb: 0.75 }}>
          {suitability.recommendation}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
          {suitability.caveat}
        </Typography>
      </Box>

      {/* Chart */}
      <Box sx={{ mt: 1.5 }}>
        <GuideSuitabilityChart
          effectiveErrorMainPixels={suitability.effective_error_main_pixels}
          rating={suitability.rating}
          ratingReason={suitability.rating_reason}
        />
      </Box>

      {suitability.guide_binning > 1 && (
        <Typography variant="caption" color="text.secondary" sx={{ fontStyle: "italic", display: "block", mt: 0.5, maxWidth: 500 }}>
          Binning improves guide-star SNR, which can partially offset the angular-resolution
          cost. This calculator shows the angular cost only.
        </Typography>
      )}

      {/* Advanced disclosure: centroid accuracy */}
      <Box sx={{ mt: 1.5 }}>
        <Box
          sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: "pointer" }}
          onClick={() => setAdvancedOpen((v) => !v)}
        >
          <IconButton size="small" sx={{ p: 0 }}>
            <ExpandMoreIcon
              sx={{
                transform: advancedOpen ? "rotate(180deg)" : "none",
                transition: "transform 0.2s",
                fontSize: 18,
              }}
            />
          </IconButton>
          <Typography variant="caption" color="text.secondary">
            Advanced
          </Typography>
        </Box>
        <Collapse in={advancedOpen}>
          <Box sx={{ pt: 1, maxWidth: 400 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
              Assumed centroid accuracy: {centroidAccuracy.toFixed(2)} px
            </Typography>
            <Slider
              value={centroidAccuracy}
              min={0.05}
              max={0.5}
              step={0.05}
              onChange={(_, v) => onCentroidChange(v as number)}
              valueLabelDisplay="auto"
              valueLabelFormat={(v) => `${v.toFixed(2)} px`}
              sx={{ maxWidth: 350 }}
            />
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", lineHeight: 1.4 }}>
              PHD2 typically resolves star centroids to about 0.1\u20130.2 pixels. Lower
              this if you have a steady mount and good guide stars; raise it if your
              guide RMS suggests worse performance.
            </Typography>
          </Box>
        </Collapse>
      </Box>

      <CalculatorAboutSection>
        <Typography variant="body2" component="p">
          <strong>Attribution.</strong> Inspired by the{" "}
          <Link
            href="https://astronomy.tools/calculators/guidescope_suitability"
            target="_blank"
            rel="noopener noreferrer"
            underline="hover"
          >
            astronomy.tools Guidescope Suitability Calculator
          </Link>
          , with refinements from{" "}
          <Link
            href="https://groups.google.com/g/open-phd-guiding"
            target="_blank"
            rel="noopener noreferrer"
            underline="hover"
          >
            Open PHD Guiding
          </Link>{" "}
          discussions and Stan Moore&apos;s{" "}
          <Link
            href="https://www.wilmslowastro.com/tips/autoguiding.htm"
            target="_blank"
            rel="noopener noreferrer"
            underline="hover"
          >
            &ldquo;Thoughts on Auto-Guiding&rdquo;
          </Link>
          .
        </Typography>
        <Typography variant="body2" component="p">
          <strong>Methodology.</strong> Evaluates whether your guide system can
          resolve errors finely enough for your imaging rig. Computes guide
          image scale from{" "}
          <code>(guide_pixel_size / guide_focal_length) × 206.265</code>,
          factoring in guide camera binning. OAG setups use the main scope&apos;s
          focal length; guide-scope setups use the guide scope&apos;s.
        </Typography>
        <Typography variant="body2" component="p">
          The headline metric is <strong>effective error in main pixels</strong>{" "}
          (<code>G-ratio × centroid_accuracy</code>, where centroid accuracy
          defaults to 0.2 px — typical PHD2 performance). Ratings:{" "}
          <strong>Excellent</strong> (≤0.6), <strong>Good</strong> (≤1.0),{" "}
          <strong>Marginal</strong> (≤1.2), <strong>Poor</strong> (&gt;1.2). A
          hard cap also rates any guide scale coarser than 6″/pixel as Poor
          regardless of ratio, reflecting PHD2 community consensus that guiding
          becomes unreliable beyond this resolution.
        </Typography>
      </CalculatorAboutSection>
    </Box>
  );
}

function MetricRow({
  label,
  value,
  subvalue,
  tooltips,
}: {
  label: string;
  value: string;
  subvalue?: string;
  tooltips: Record<string, string>;
}) {
  const tooltip = tooltips[label];
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
        <Typography variant="body1">{value}</Typography>
        {subvalue && (
          <Typography variant="caption" color="text.secondary">
            {subvalue}
          </Typography>
        )}
      </td>
    </tr>
  );
}
