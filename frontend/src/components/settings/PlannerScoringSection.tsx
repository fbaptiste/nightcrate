/**
 * Planner Scoring section on the Settings page (v0.21.0). One collapsible
 * Accordion per parameter family so the page doesn't balloon with ~25
 * controls. Backend model validator rejects invalid combinations.
 */
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import type { Settings } from "@/api/settings";
import { useSettingsStore } from "@/stores/settingsStore";

interface Props {
  settings: Settings;
}

export function PlannerScoringSection({ settings }: Props) {
  const update = useSettingsStore((s) => s.update);

  return (
    <Accordion variant="outlined" disableGutters defaultExpanded={false} sx={{ breakInside: "avoid", mb: 1 }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography
          variant="body2"
          color="text.secondary"
          fontWeight={500}
          sx={{
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            fontSize: "0.7rem",
          }}
        >
          Planner Scoring
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        <FormHelperText sx={{ mb: 1, ml: 0 }}>
          Tunes the 0-100 quality score on the Planner. See
          <code> docs/planner-scoring.md</code> for the full algorithm.
        </FormHelperText>

        <ScoringAccordion title="Combination weights">
          <FormHelperText sx={{ mb: 2, ml: 0 }}>
            Relative importance of each quality dimension. The final
            score is a weighted geometric mean, so a zero effectively
            removes a dimension.
          </FormHelperText>
          <WeightSlider
            label="Observability"
            tooltip="How much high-altitude observation time the target gets during astro-dark. Default: 2.0 (the most important factor — no amount of cleverness fixes a target that's barely up). Example: set to 1.0 if you care equally about meridian timing."
            value={settings.scoring_weight_observability}
            onChange={(v) => update({ scoring_weight_observability: v })}
          />
          <WeightSlider
            label="Meridian timing"
            tooltip="How close the target's peak altitude falls to the middle of astro-dark. Default: 1.0. Example: set to 0 if you don't care whether a target transits early or late."
            value={settings.scoring_weight_meridian}
            onChange={(v) => update({ scoring_weight_meridian: v })}
          />
          <WeightSlider
            label="Moon impact"
            tooltip="How much moonlight will contaminate your filter choice. Default: 1.5 (second-most-important because moon varies night-to-night). Example: set to 0 if you only shoot Ha or if you're at a dark site and never notice the moon."
            value={settings.scoring_weight_moon}
            onChange={(v) => update({ scoring_weight_moon: v })}
          />
          <WeightSlider
            label="Frame fit"
            tooltip="How well the target fills your selected rig's field of view. Default: 1.0. Example: raise to 3.0 if you obsess over composition and want framing to dominate ranking."
            value={settings.scoring_weight_frame_fit}
            onChange={(v) => update({ scoring_weight_frame_fit: v })}
          />
        </ScoringAccordion>

        <ScoringAccordion title="Moon — filter sensitivities">
          <FormHelperText sx={{ mb: 2, ml: 0 }}>
            How susceptible each filter line is to moonlight. 0.0 =
            immune, 1.0 = broadband-equivalent. The most sensitive
            filter in your session intent bounds the whole session.
          </FormHelperText>
          <SensitivitySlider
            label="Hα (656 nm)"
            tooltip="Deep red narrowband — very tolerant of moon. Default: 0.15. Example: lower to 0.05 if you have a premium 3-nm Hα filter."
            value={settings.scoring_moon_sensitivity_ha}
            onChange={(v) => update({ scoring_moon_sensitivity_ha: v })}
          />
          <SensitivitySlider
            label="SII (672 nm)"
            tooltip="Deep red narrowband — similar to Hα. Default: 0.25. SII is slightly more affected than Hα because the filter is harder to produce narrow."
            value={settings.scoring_moon_sensitivity_sii}
            onChange={(v) => update({ scoring_moon_sensitivity_sii: v })}
          />
          <SensitivitySlider
            label="OIII (501 nm)"
            tooltip="Blue-green narrowband. Default: 0.70. Much more affected than Hα because moonlight is bright around 500 nm. Example: 0.40 for a 3-nm Chroma in a dark-site scenario."
            value={settings.scoring_moon_sensitivity_oiii}
            onChange={(v) => update({ scoring_moon_sensitivity_oiii: v })}
          />
          <SensitivitySlider
            label="Luminance"
            tooltip="Broadband full visible. Default: 0.95. Essentially fully exposed to the moon."
            value={settings.scoring_moon_sensitivity_l}
            onChange={(v) => update({ scoring_moon_sensitivity_l: v })}
          />
          <SensitivitySlider
            label="Red"
            tooltip="Broadband red (~620 nm). Default: 0.55. Less affected than green/blue because Rayleigh scattering drops at longer wavelengths."
            value={settings.scoring_moon_sensitivity_r}
            onChange={(v) => update({ scoring_moon_sensitivity_r: v })}
          />
          <SensitivitySlider
            label="Green"
            tooltip="Broadband green (~530 nm). Default: 0.85. Near moonlight's peak wavelength."
            value={settings.scoring_moon_sensitivity_g}
            onChange={(v) => update({ scoring_moon_sensitivity_g: v })}
          />
          <SensitivitySlider
            label="Blue"
            tooltip="Broadband blue (~430 nm). Default: 1.00. Most affected of all — Rayleigh scattering favors short wavelengths."
            value={settings.scoring_moon_sensitivity_b}
            onChange={(v) => update({ scoring_moon_sensitivity_b: v })}
          />
        </ScoringAccordion>

        <ScoringAccordion title="Moon — minimum separation (°)">
          <FormHelperText sx={{ mb: 2, ml: 0 }}>
            Angular distance from the moon below which impact is
            considered maximal. The per-time proximity factor
            interpolates from 0 (at the moon) to 1 (beyond this).
          </FormHelperText>
          {[
            ["Hα", "ha"],
            ["SII", "sii"],
            ["OIII", "oiii"],
            ["L", "l"],
            ["R", "r"],
            ["G", "g"],
            ["B", "b"],
          ].map(([label, key]) => (
            <SeparationSlider
              key={key}
              label={label}
              tooltip={`Minimum "safe" separation for ${label}. Default: ${
                (settings as unknown as Record<string, number>)[
                  `scoring_moon_min_sep_${key}`
                ]
              }°. Example: raise if you shoot conservatively; lower if you've verified you can shoot closer to the moon with this filter.`}
              value={
                (settings as unknown as Record<string, number>)[
                  `scoring_moon_min_sep_${key}`
                ]
              }
              onChange={(v) => update({ [`scoring_moon_min_sep_${key}`]: v } as Partial<Settings>)}
            />
          ))}
        </ScoringAccordion>

        <ScoringAccordion title="Moon — cluster modifier">
          <Box sx={{ mb: 2 }}>
            <Tooltip
              title="How much moon-tolerance softening open clusters, globular clusters, and stellar associations get. 0.5 (default) = clusters experience half the moon impact of non-cluster targets. Example: 0.3 if you find clusters essentially moon-proof; 1.0 to disable the softening entirely."
              placement="top"
              arrow
            >
              <Typography variant="body1" gutterBottom sx={{ cursor: "help" }}>
                Cluster moon modifier: {settings.scoring_cluster_moon_modifier.toFixed(2)}
              </Typography>
            </Tooltip>
            <Slider
              size="small"
              value={settings.scoring_cluster_moon_modifier}
              min={0}
              max={1}
              step={0.05}
              onChange={(_, v) =>
                update({ scoring_cluster_moon_modifier: v as number })
              }
              sx={{ maxWidth: 360 }}
            />
          </Box>
        </ScoringAccordion>

        <ScoringAccordion title="Observability & frame fit">
          <Box sx={{ mb: 2 }}>
            <Tooltip
              title="Altitude below which a target is not counted as observable. Also anchors the airmass-quality curve. Default: 30°. Example: 20° if you have low local horizons and routinely image below 30°."
              placement="top"
              arrow
            >
              <Typography variant="body1" gutterBottom sx={{ cursor: "help" }}>
                Min observability altitude: {settings.scoring_observability_min_altitude_deg.toFixed(0)}°
              </Typography>
            </Tooltip>
            <Slider
              size="small"
              value={settings.scoring_observability_min_altitude_deg}
              min={5}
              max={60}
              step={1}
              onChange={(_, v) =>
                update({ scoring_observability_min_altitude_deg: v as number })
              }
              sx={{ maxWidth: 360 }}
            />
          </Box>
          <Box sx={{ mb: 2 }}>
            <Tooltip
              title="Coverage % that scores a perfect 1.0 in the frame-fit Gaussian. Default: 55%. Example: 130 for mosaic fans who want overflow targets to win; 15 for galaxy hunters on long focal lengths."
              placement="top"
              arrow
            >
              <Typography variant="body1" gutterBottom sx={{ cursor: "help" }}>
                Frame-fit ideal coverage: {settings.scoring_frame_fit_ideal_coverage_pct.toFixed(0)}%
              </Typography>
            </Tooltip>
            <Slider
              size="small"
              value={settings.scoring_frame_fit_ideal_coverage_pct}
              min={1}
              max={500}
              step={5}
              onChange={(_, v) =>
                update({ scoring_frame_fit_ideal_coverage_pct: v as number })
              }
              sx={{ maxWidth: 360 }}
            />
          </Box>
          <Box sx={{ mb: 2 }}>
            <Tooltip
              title="Width of the frame-fit curve. Smaller = more demanding (punishes any deviation from ideal). Larger = more forgiving. Default: 35. Example: 20 for tight-crop framers; 50 to let anything within 2× of ideal score well."
              placement="top"
              arrow
            >
              <Typography variant="body1" gutterBottom sx={{ cursor: "help" }}>
                Frame-fit spread: {settings.scoring_frame_fit_spread.toFixed(0)}
              </Typography>
            </Tooltip>
            <Slider
              size="small"
              value={settings.scoring_frame_fit_spread}
              min={5}
              max={100}
              step={1}
              onChange={(_, v) =>
                update({ scoring_frame_fit_spread: v as number })
              }
              sx={{ maxWidth: 360 }}
            />
          </Box>
        </ScoringAccordion>

        <ScoringAccordion title="Hard gates">
          <Box sx={{ mb: 2 }}>
            <Tooltip
              title="Targets observable for less than this many hours during astro-dark are gated out (score=—). Default: 1.0 h. Example: 0.25 if you're willing to shoot 15-minute windows; 2.0 if you only want serious targets."
              placement="top"
              arrow
            >
              <Typography variant="body1" gutterBottom sx={{ cursor: "help" }}>
                Minimum observable hours: {settings.scoring_gate_min_obs_hours.toFixed(1)} h
              </Typography>
            </Tooltip>
            <Slider
              size="small"
              value={settings.scoring_gate_min_obs_hours}
              min={0}
              max={12}
              step={0.25}
              onChange={(_, v) =>
                update({ scoring_gate_min_obs_hours: v as number })
              }
              sx={{ maxWidth: 360 }}
            />
          </Box>
          <Box sx={{ mb: 2 }}>
            <Tooltip
              title="Coverage % above which a target is gated out of scoring (not the same as the list filter — this removes from SCORING only). Disabled by default; the frame-fit curve handles oversized targets gracefully. Example: 100 to gate out mosaic-scale targets entirely."
              placement="top"
              arrow
            >
              <Typography variant="body1" gutterBottom sx={{ cursor: "help" }}>
                Max coverage gate:{" "}
                {settings.scoring_gate_max_coverage_pct == null
                  ? "disabled"
                  : `${settings.scoring_gate_max_coverage_pct.toFixed(0)}%`}
              </Typography>
            </Tooltip>
            <Stack direction="row" spacing={1} alignItems="center">
              <FormControl size="small" sx={{ minWidth: 140 }}>
                <InputLabel id="max-coverage-mode">Mode</InputLabel>
                <Select
                  labelId="max-coverage-mode"
                  label="Mode"
                  value={settings.scoring_gate_max_coverage_pct == null ? "off" : "on"}
                  onChange={(e) =>
                    update({
                      scoring_gate_max_coverage_pct:
                        e.target.value === "off" ? null : 100.0,
                    })
                  }
                >
                  <MenuItem value="off">Disabled</MenuItem>
                  <MenuItem value="on">Enabled</MenuItem>
                </Select>
              </FormControl>
              {settings.scoring_gate_max_coverage_pct != null && (
                <TextField
                  type="number"
                  size="small"
                  value={settings.scoring_gate_max_coverage_pct}
                  onChange={(e) => {
                    const n = parseFloat(e.target.value);
                    if (!isNaN(n) && n >= 50 && n <= 500) {
                      update({ scoring_gate_max_coverage_pct: n });
                    }
                  }}
                  inputProps={{ min: 50, max: 500, step: 5 }}
                  sx={{ width: 100 }}
                />
              )}
            </Stack>
          </Box>
        </ScoringAccordion>

        <ScoringAccordion title="Quality labels">
          <FormHelperText sx={{ mb: 2, ml: 0 }}>
            Score boundaries for the chip label. Must satisfy
            excellent &gt; good &gt; fair.
          </FormHelperText>
          <ThresholdField
            label="Excellent ≥"
            tooltip="Score at or above this → 'Excellent'. Default: 80. Example: raise to 90 if you want the label reserved for near-ideal nights."
            value={settings.scoring_threshold_excellent}
            onChange={(v) => update({ scoring_threshold_excellent: v })}
          />
          <ThresholdField
            label="Good ≥"
            tooltip="Score at or above this but below Excellent → 'Good'. Default: 60."
            value={settings.scoring_threshold_good}
            onChange={(v) => update({ scoring_threshold_good: v })}
          />
          <ThresholdField
            label="Fair ≥"
            tooltip="Score at or above this but below Good → 'Fair'. Below this → 'Poor'. Default: 40."
            value={settings.scoring_threshold_fair}
            onChange={(v) => update({ scoring_threshold_fair: v })}
          />
        </ScoringAccordion>
      </AccordionDetails>
    </Accordion>
  );
}


// ── Local sub-components ──────────────────────────────────────────


function ScoringAccordion({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Accordion
      disableGutters
      elevation={0}
      sx={{
        "&:before": { display: "none" },
        border: "1px solid",
        borderColor: "divider",
        mb: 1,
      }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="body2" fontWeight={500}>
          {title}
        </Typography>
      </AccordionSummary>
      <AccordionDetails>{children}</AccordionDetails>
    </Accordion>
  );
}


function WeightSlider({
  label,
  tooltip,
  value,
  onChange,
}: {
  label: string;
  tooltip: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <Box sx={{ mb: 2 }}>
      <Tooltip title={tooltip} placement="top" arrow>
        <Typography variant="body2" gutterBottom sx={{ cursor: "help" }}>
          {label} weight: {value.toFixed(2)}
        </Typography>
      </Tooltip>
      <Slider
        size="small"
        value={value}
        min={0}
        max={10}
        step={0.1}
        onChange={(_, v) => onChange(v as number)}
        sx={{ maxWidth: 360 }}
      />
    </Box>
  );
}


function SensitivitySlider({
  label,
  tooltip,
  value,
  onChange,
}: {
  label: string;
  tooltip: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <Box sx={{ mb: 2 }}>
      <Tooltip title={tooltip} placement="top" arrow>
        <Typography variant="body2" gutterBottom sx={{ cursor: "help" }}>
          {label}: {value.toFixed(2)}
        </Typography>
      </Tooltip>
      <Slider
        size="small"
        value={value}
        min={0}
        max={1}
        step={0.05}
        onChange={(_, v) => onChange(v as number)}
        sx={{ maxWidth: 360 }}
      />
    </Box>
  );
}


function SeparationSlider({
  label,
  tooltip,
  value,
  onChange,
}: {
  label: string;
  tooltip: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <Box sx={{ mb: 2 }}>
      <Tooltip title={tooltip} placement="top" arrow>
        <Typography variant="body2" gutterBottom sx={{ cursor: "help" }}>
          {label}: {value.toFixed(0)}°
        </Typography>
      </Tooltip>
      <Slider
        size="small"
        value={value}
        min={10}
        max={180}
        step={5}
        onChange={(_, v) => onChange(v as number)}
        sx={{ maxWidth: 360 }}
      />
    </Box>
  );
}


function ThresholdField({
  label,
  tooltip,
  value,
  onChange,
}: {
  label: string;
  tooltip: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <Box sx={{ mb: 2 }}>
      <Tooltip title={tooltip} placement="top" arrow>
        <Typography variant="body2" gutterBottom sx={{ cursor: "help" }}>
          {label} {value}
        </Typography>
      </Tooltip>
      <TextField
        type="number"
        size="small"
        value={value}
        onChange={(e) => {
          const n = parseInt(e.target.value, 10);
          if (!isNaN(n) && n >= 0 && n <= 100) onChange(n);
        }}
        inputProps={{ min: 0, max: 100, step: 1 }}
        sx={{ width: 100 }}
      />
    </Box>
  );
}
