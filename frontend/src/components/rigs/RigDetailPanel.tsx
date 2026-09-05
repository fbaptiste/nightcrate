import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import CalculatorPanel from "@/components/rigs/CalculatorPanel";
import type { Rig } from "@/api/rigs";

/** A labelled value. Rendered only when there is something to show. */
function Field({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <Box sx={{ display: "flex", gap: 1, py: 0.25, minWidth: 0 }}>
      <Typography
        variant="body2"
        sx={{ color: "text.secondary", minWidth: 132, flexShrink: 0 }}
      >
        {label}
      </Typography>
      <Typography variant="body2" sx={{ minWidth: 0, wordBreak: "break-word" }}>
        {value}
      </Typography>
    </Box>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Box sx={{ mb: 2, minWidth: 0 }}>
      <Typography
        variant="subtitle2"
        sx={{ mb: 0.5, textTransform: "uppercase", letterSpacing: 0.5, fontSize: "0.7rem" }}
      >
        {title}
      </Typography>
      {children}
    </Box>
  );
}

/**
 * Everything about one rig, in full.
 *
 * The card is deliberately a summary — name, optics, filter count — so this is
 * where the rest lives: the equipment that makes up the rig, the sensor, the
 * individual filters in each slot, and the derived calculations.
 */
export default function RigDetailPanel({ rig }: { rig: Rig }) {
  const slots = [...rig.filter_slots].sort((a, b) => a.slot_number - b.slot_number);
  const sensor =
    rig.sensor_resolution_x && rig.sensor_resolution_y
      ? `${rig.sensor_resolution_x} × ${rig.sensor_resolution_y}`
      : null;
  const sensorSize =
    rig.sensor_width_mm && rig.sensor_height_mm
      ? `${rig.sensor_width_mm} × ${rig.sensor_height_mm} mm`
      : null;

  return (
    <Box sx={{ pr: 4 }}>
      <Typography variant="h6" sx={{ mb: 0.25 }}>
        {rig.name}
      </Typography>
      {rig.description && (
        <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
          {rig.description}
        </Typography>
      )}

      {/* Two columns on a wide screen, one when there isn't room. */}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
          columnGap: 4,
        }}
      >
        <Section title="Optics">
          <Field label="OTA" value={rig.telescope_name} />
          <Field label="Configuration" value={rig.telescope_config_name} />
          <Field label="Aperture" value={`${rig.aperture_mm} mm`} />
          <Field label="Focal length" value={`${rig.effective_focal_length_mm} mm`} />
          <Field label="Focal ratio" value={`f/${rig.effective_focal_ratio}`} />
          <Field
            label="Image circle"
            value={
              rig.calculators.image_circle_mm
                ? `${rig.calculators.image_circle_mm} mm`
                : null
            }
          />
        </Section>

        <Section title="Camera">
          <Field label="Camera" value={rig.camera_name} />
          <Field label="Sensor type" value={rig.sensor_type} />
          <Field label="Resolution" value={sensor} />
          <Field label="Pixel size" value={rig.pixel_size_um ? `${rig.pixel_size_um} µm` : null} />
          <Field label="Sensor size" value={sensorSize} />
          <Field
            label="ADC depth"
            value={rig.sensor_adc_bit_depth ? `${rig.sensor_adc_bit_depth}-bit` : null}
          />
        </Section>

        <Section title="Filters">
          {rig.filter_wheel_name ? (
            <>
              <Field label="Filter wheel" value={rig.filter_wheel_name} />
              <Field label="Positions" value={rig.filter_wheel_positions} />
              {slots.length > 0 ? (
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.5 }}>
                  {slots.map((s) => (
                    <Chip
                      key={s.slot_number}
                      size="small"
                      variant="outlined"
                      label={`${s.slot_number}. ${s.filter_name}`}
                    />
                  ))}
                </Box>
              ) : (
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  No filters assigned
                </Typography>
              )}
            </>
          ) : rig.single_filter_name ? (
            <Field label="Filter" value={rig.single_filter_name} />
          ) : (
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              No filter wheel
            </Typography>
          )}
        </Section>

        <Section title="Mount &amp; guiding">
          <Field label="Mount" value={rig.mount_name} />
          <Field label="Focuser" value={rig.focuser_name} />
          <Field label="Off-axis guider" value={rig.oag_name} />
          <Field
            label="Guide scope"
            value={
              rig.guide_scope_name
                ? rig.guide_scope_focal_length_mm
                  ? `${rig.guide_scope_name} (${rig.guide_scope_focal_length_mm} mm)`
                  : rig.guide_scope_name
                : null
            }
          />
          <Field label="Guide camera" value={rig.guide_camera_name} />
          {!rig.mount_name && !rig.oag_name && !rig.guide_scope_name && (
            <Typography variant="body2" sx={{ color: "text.secondary" }}>
              Self-contained &mdash; no separate mount or guiding
            </Typography>
          )}
        </Section>

        {(rig.computer_name || rig.software.length > 0) && (
          <Section title="Control">
            <Field label="Computer" value={rig.computer_name} />
            <Field
              label="Software"
              value={rig.software.map((s) => s.name).join(", ") || null}
            />
          </Section>
        )}

        {rig.notes && (
          <Section title="Notes">
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
              {rig.notes}
            </Typography>
          </Section>
        )}
      </Box>

      {rig.warnings.length > 0 && (
        <Box sx={{ mb: 2 }}>
          {rig.warnings.map((w, i) => (
            <Typography key={i} variant="body2" sx={{ color: "warning.main" }}>
              {w.message}
            </Typography>
          ))}
        </Box>
      )}

      <Divider sx={{ my: 2 }} />
      <CalculatorPanel rig={rig} />
    </Box>
  );
}
