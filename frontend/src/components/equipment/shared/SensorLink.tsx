import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import type { Sensor } from "@/api/equipment";

function PopoverRow({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: "flex", gap: 1, py: 0.15 }}>
      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 90 }}>
        {label}
      </Typography>
      <Typography variant="caption">{value}</Typography>
    </Box>
  );
}

interface SensorLinkProps {
  sensor: Sensor;
}

/** Sensor name that shows a spec popover on hover and navigates to the sensor page on click. */
export default function SensorLink({ sensor }: SensorLinkProps) {
  const navigate = useNavigate();
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const [open, setOpen] = useState(false);

  const handleClick = () => {
    setOpen(false);
    navigate(`/equipment/sensors?select=${sensor.id}`);
  };

  return (
    <>
      <Typography
        ref={anchorRef}
        variant="body2"
        component="span"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onClick={handleClick}
        sx={{
          color: "primary.main",
          cursor: "pointer",
          textDecoration: "none",
          "&:hover": { textDecoration: "underline" },
        }}
      >
        {sensor.model_name}
      </Typography>
      <Popover
        open={open}
        anchorEl={anchorRef.current}
        onClose={() => setOpen(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        sx={{ pointerEvents: "none", mt: 0.5 }}
        disableRestoreFocus
      >
        <Box sx={{ p: 1.5, maxWidth: 320 }}>
          <Typography variant="subtitle2" gutterBottom>
            {sensor.manufacturer.name} {sensor.model_name}
          </Typography>
          <PopoverRow label="Type" value={sensor.sensor_type} />
          <PopoverRow
            label="Resolution"
            value={`${sensor.resolution_x} × ${sensor.resolution_y}`}
          />
          <PopoverRow label="Pixel Size" value={`${sensor.pixel_size_um} μm`} />
          {sensor.sensor_width_mm != null && sensor.sensor_height_mm != null && (
            <PopoverRow
              label="Dimensions"
              value={`${sensor.sensor_width_mm} × ${sensor.sensor_height_mm} mm`}
            />
          )}
          {sensor.adc_bit_depth != null && (
            <PopoverRow label="ADC" value={`${sensor.adc_bit_depth}-bit`} />
          )}
          {sensor.full_well_capacity_ke != null && (
            <PopoverRow label="Full Well" value={`${sensor.full_well_capacity_ke} Ke-`} />
          )}
          {sensor.read_noise_e != null && (
            <PopoverRow label="Read Noise" value={`${sensor.read_noise_e} e-`} />
          )}
          {sensor.peak_qe_pct != null && (
            <PopoverRow label="Peak QE" value={`${sensor.peak_qe_pct}%`} />
          )}
          {sensor.bayer_pattern && (
            <PopoverRow label="Bayer" value={sensor.bayer_pattern} />
          )}
          <PopoverRow label="Dual Gain" value={sensor.dual_gain ? "Yes" : "No"} />
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 0.5, fontStyle: "italic" }}
          >
            Click to view sensor details
          </Typography>
        </Box>
      </Popover>
    </>
  );
}
