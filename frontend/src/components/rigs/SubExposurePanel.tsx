import { useState } from "react";
import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Slider from "@mui/material/Slider";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import type { SubExposureCalc, SubExposureResult } from "@/api/rigs";
import { RIG_ORANGE } from "@/lib/rigColors";

interface SubExposurePanelProps {
  subExposure: SubExposureCalc | null;
  kFactor: number;
  onKFactorChange: (k: number) => void;
}

export default function SubExposurePanel({
  subExposure,
  kFactor,
  onKFactorChange,
}: SubExposurePanelProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
        Sub-Exposure
      </Typography>

      {subExposure === null ? (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", fontStyle: "italic" }}
        >
          Sub-exposure cannot be calculated. The imaging sensor is missing one
          or more photometric values (read noise, peak QE, or full well
          capacity). Edit the sensor equipment record to add them.
        </Typography>
      ) : (
        <>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mb: 1 }}
          >
            Sky: {subExposure.sky_brightness_source_detail}
            {" \u2022 "}Read noise: {subExposure.read_noise_e.toFixed(1)}e
            {"\u207b"}
            {" \u2022 "}QE: {subExposure.peak_qe_pct.toFixed(0)}%
          </Typography>

          <Box
            component="table"
            sx={{
              width: "100%",
              maxWidth: 720,
              borderCollapse: "collapse",
              "& td, & th": {
                py: 0.5,
                px: 1,
                textAlign: "left",
                fontSize: "0.875rem",
                borderBottom: 1,
                borderColor: "divider",
              },
              "& th": {
                color: "text.secondary",
                fontWeight: 500,
                fontSize: "0.75rem",
                textTransform: "uppercase",
                letterSpacing: 0.4,
              },
            }}
          >
            <thead>
              <tr>
                <th>Slot</th>
                <th>Filter</th>
                <th>Bandpass</th>
                <th>Sky Rate</th>
                <th>Optimal</th>
                <th>Suggested</th>
              </tr>
            </thead>
            <tbody>
              {subExposure.results.map((r) => (
                <SubExposureRow
                  key={`${r.filter_id ?? "unfiltered"}-${r.filter_slot_number ?? 0}`}
                  r={r}
                />
              ))}
            </tbody>
          </Box>

          <Box sx={{ mt: 1.5 }}>
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 0.5,
                cursor: "pointer",
              }}
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
              <Box sx={{ pt: 1, maxWidth: 500 }}>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: "block", mb: 0.5 }}
                >
                  Read-noise allowance (k): {kFactor.toFixed(0)}
                </Typography>
                <Slider
                  value={kFactor}
                  min={3}
                  max={20}
                  step={1}
                  onChange={(_, v) => onKFactorChange(v as number)}
                  valueLabelDisplay="auto"
                  marks={[
                    { value: 3, label: "3" },
                    { value: 10, label: "10" },
                    { value: 20, label: "20" },
                  ]}
                  sx={{ maxWidth: 400 }}
                />
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: "block", lineHeight: 1.4, mt: 0.5 }}
                >
                  Lower k allows read noise to contribute more to total noise
                  (shorter subs). Higher k swamps read noise more completely
                  (longer subs). Glover&apos;s recommended default is 10.
                </Typography>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{
                    display: "block",
                    mt: 1.5,
                    fontStyle: "italic",
                    lineHeight: 1.4,
                  }}
                >
                  This calculation uses peak sensor QE and peak filter
                  transmission as proxies for wavelength-averaged values, and
                  assumes a spectrally flat sky — collectively worth roughly
                  &plusmn;30% error. Round aggressively and trust the standard
                  sub-length column.
                </Typography>
              </Box>
            </Collapse>
          </Box>
        </>
      )}
    </Box>
  );
}

function SubExposureRow({ r }: { r: SubExposureResult }) {
  return (
    <tr>
      <td>{r.filter_slot_number ?? "\u2014"}</td>
      <td>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          {r.filter_label}
          {!r.has_passband_data && (
            <Tooltip
              title="No passband data on file — using type-based defaults. Edit the filter to improve accuracy."
              arrow
              placement="top"
            >
              <InfoOutlinedIcon
                sx={{ fontSize: 14, color: "text.secondary" }}
              />
            </Tooltip>
          )}
        </Box>
      </td>
      <td>
        {r.effective_bandpass_nm.toFixed(0)} nm (
        {r.filter_transmission_pct.toFixed(0)}%)
      </td>
      <td>{r.sky_rate_e_per_s_per_pixel.toFixed(2)} e⁻/s</td>
      <td>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Typography component="span" variant="body2">
            {r.optimal_sub_seconds >= 60
              ? `${Math.round(r.optimal_sub_seconds)} s`
              : `${r.optimal_sub_seconds.toFixed(1)} s`}
          </Typography>
          {r.saturation_capped && (
            <Tooltip
              title={`Sky saturates the sensor at ${Math.round(r.saturation_sub_seconds)}s — recommended value is capped.`}
              arrow
            >
              <WarningAmberIcon
                sx={{ fontSize: 14, color: RIG_ORANGE }}
              />
            </Tooltip>
          )}
        </Box>
      </td>
      <td>
        <Typography component="span" variant="body2" sx={{ fontWeight: 600 }}>
          {r.standard_sub_seconds} s
        </Typography>
      </td>
    </tr>
  );
}
