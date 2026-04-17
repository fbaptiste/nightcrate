import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import { useTheme } from "@mui/material/styles";
import Typography from "@mui/material/Typography";
import type { GuidingTolerance } from "@/api/rigs";
import {
  RIG_BLUE,
  RIG_BLUE_LIGHT,
  RIG_ORANGE_LIGHT,
} from "@/lib/rigColors";
import CalculatorAboutSection from "./CalculatorAboutSection";

interface GuidingTolerancePanelProps {
  tolerance: GuidingTolerance;
}

export default function GuidingTolerancePanel({
  tolerance,
}: GuidingTolerancePanelProps) {
  const theme = useTheme();
  const isDark = theme.palette.mode === "dark";

  const gridBg = isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.02)";
  // X-axis max: a bit past the noticeable threshold or the current precision.
  const xMax = Math.max(tolerance.noticeable_rms_arcsec * 1.2, 1);
  const current = tolerance.current_guide_precision_arcsec;

  const pct = (v: number) => `${(Math.min(v, xMax) / xMax) * 100}%`;

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.25 }}>
        Guiding Tolerance
      </Typography>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mb: 1 }}
      >
        How much PHD2 RMS your rig can tolerate before stars elongate. At{" "}
        {tolerance.image_binning}&times;{tolerance.image_binning} binning (main
        scale {tolerance.main_scale_arcsec_per_pixel.toFixed(2)}
        &Prime;/px).
      </Typography>

      {/* Thresholds block */}
      <Box
        component="table"
        sx={{
          borderCollapse: "collapse",
          mb: 1.5,
          "& td, & th": {
            py: 0.5,
            pr: 2,
            textAlign: "left",
            fontSize: "0.875rem",
            borderBottom: 1,
            borderColor: "divider",
          },
          "& th": { color: "text.secondary", fontWeight: 500 },
        }}
      >
        <thead>
          <tr>
            <th>Budget</th>
            <th>RMS threshold</th>
            <th>Meaning</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>
              <Typography
                component="span"
                variant="body2"
                sx={{ color: RIG_BLUE, fontWeight: 600 }}
              >
                Tight
              </Typography>
            </td>
            <td>
              &le; {tolerance.tight_rms_arcsec.toFixed(2)}&Prime;
            </td>
            <td>Stars stay round</td>
          </tr>
          <tr>
            <td>
              <Typography
                component="span"
                variant="body2"
                sx={{ color: RIG_BLUE_LIGHT, fontWeight: 600 }}
              >
                Acceptable
              </Typography>
            </td>
            <td>
              &le; {tolerance.acceptable_rms_arcsec.toFixed(2)}&Prime;
            </td>
            <td>Elongation barely noticeable</td>
          </tr>
          <tr>
            <td>
              <Typography
                component="span"
                variant="body2"
                sx={{ color: RIG_ORANGE_LIGHT, fontWeight: 600 }}
              >
                Over budget
              </Typography>
            </td>
            <td>
              &gt; {tolerance.acceptable_rms_arcsec.toFixed(2)}&Prime;
            </td>
            <td>Elongation visible</td>
          </tr>
        </tbody>
      </Box>

      {/* Visualization: shaded zones along an arcsec axis */}
      <Box sx={{ maxWidth: 500, mb: 1 }}>
        <Box
          sx={{
            position: "relative",
            height: 24,
            bgcolor: gridBg,
            borderRadius: 1,
            overflow: "hidden",
          }}
        >
          <Box
            sx={{
              position: "absolute",
              left: 0,
              top: 0,
              bottom: 0,
              width: pct(tolerance.tight_rms_arcsec),
              bgcolor: RIG_BLUE,
              opacity: 0.35,
            }}
          />
          <Box
            sx={{
              position: "absolute",
              left: pct(tolerance.tight_rms_arcsec),
              top: 0,
              bottom: 0,
              width: `calc(${pct(tolerance.acceptable_rms_arcsec)} - ${pct(tolerance.tight_rms_arcsec)})`,
              bgcolor: RIG_BLUE_LIGHT,
              opacity: 0.35,
            }}
          />
          <Box
            sx={{
              position: "absolute",
              left: pct(tolerance.acceptable_rms_arcsec),
              right: 0,
              top: 0,
              bottom: 0,
              bgcolor: RIG_ORANGE_LIGHT,
              opacity: 0.35,
            }}
          />
          {current !== null && (
            <Box
              sx={{
                position: "absolute",
                left: pct(current),
                top: 0,
                bottom: 0,
                width: "2px",
                bgcolor: "text.primary",
              }}
            />
          )}
        </Box>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            maxWidth: 500,
            mt: 0.5,
          }}
        >
          <Typography variant="caption" color="text.secondary">
            0
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {tolerance.tight_rms_arcsec.toFixed(2)}&Prime;
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {tolerance.acceptable_rms_arcsec.toFixed(2)}&Prime;
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {xMax.toFixed(2)}&Prime;
          </Typography>
        </Box>
      </Box>

      {current !== null && (
        <Typography
          variant="caption"
          sx={{ display: "block", mb: 0.5 }}
        >
          Current guide precision:{" "}
          <Box component="span" sx={{ fontWeight: 600 }}>
            {current.toFixed(2)}&Prime;
          </Box>
        </Typography>
      )}

      <Typography variant="body2">{tolerance.interpretation}</Typography>

      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mt: 1.5, fontStyle: "italic" }}
      >
        Once PHD2 logs are imported, NightCrate will compare your measured RMS
        to these thresholds automatically.
      </Typography>

      <CalculatorAboutSection>
        <Typography variant="body2" component="p">
          <strong>Attribution.</strong> Standard astrophotography rule of thumb
          that guide RMS should stay below main-camera pixel scale to avoid
          visible star elongation, widely discussed on{" "}
          <Link
            href="https://www.cloudynights.com/topic/871543-rule-of-thumb-for-guiding-accuracy/"
            target="_blank"
            rel="noopener noreferrer"
            underline="hover"
          >
            Cloudy Nights
          </Link>
          .
        </Typography>
        <Typography variant="body2" component="p">
          <strong>Methodology.</strong> The inverse question to Guide System:
          &ldquo;given my rig, what PHD2 RMS should I aim for?&rdquo; Computed
          from the main imaging scale at the selected binning:
        </Typography>
        <Box component="ul" sx={{ mt: 0, mb: 1 }}>
          <Typography component="li" variant="body2">
            <strong>Tight</strong> = 0.5 × main_scale — stars stay round
          </Typography>
          <Typography component="li" variant="body2">
            <strong>Acceptable</strong> = 1.0 × main_scale — elongation barely
            noticeable
          </Typography>
          <Typography component="li" variant="body2">
            <strong>Over budget</strong> = &gt; 1.0 × main_scale — visible
            elongation
          </Typography>
        </Box>
        <Typography variant="body2" component="p">
          Guide RMS contributes to star FWHM in quadrature with seeing and
          diffraction — errors below half a pixel disappear into the PSF,
          errors above one pixel show as clear elongation. When a guide system
          is configured, its effective precision is compared to these budgets
          with a plain-language interpretation.
        </Typography>
      </CalculatorAboutSection>
    </Box>
  );
}
