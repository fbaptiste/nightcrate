import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { Rig } from "@/api/rigs";

interface EquipmentTabProps {
  rig: Rig;
}

/**
 * Simple read-only equipment detail view. Flat layout with grouped sections.
 * Only renders sections for slots that have equipment assigned.
 */
export default function EquipmentTab({ rig }: EquipmentTabProps) {
  const sensorDims =
    rig.sensor_width_mm != null && rig.sensor_height_mm != null
      ? `${rig.sensor_width_mm} \u00d7 ${rig.sensor_height_mm} mm`
      : null;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
      {rig.description && (
        <DetailSection title="Description">
          <Typography variant="body2">{rig.description}</Typography>
        </DetailSection>
      )}

      <DetailSection title="Optical Train">
        <Field label="Telescope" value={rig.telescope_name} />
        <Field
          label="Configuration"
          value={`${rig.telescope_config_name} — ${rig.effective_focal_length_mm}mm, f/${rig.effective_focal_ratio}, ${rig.aperture_mm}mm aperture`}
        />
      </DetailSection>

      <DetailSection title="Imaging Camera">
        <Field label="Camera" value={rig.camera_name} />
        <Field
          label="Sensor"
          value={`${rig.pixel_size_um}\u00b5m pixels, ${rig.sensor_resolution_x} \u00d7 ${rig.sensor_resolution_y}${sensorDims ? ` (${sensorDims})` : ""}, ${rig.sensor_type}`}
        />
      </DetailSection>

      {(rig.filter_wheel_id || rig.single_filter_id) && (
        <DetailSection title="Filtration">
          {rig.filter_wheel_id && (
            <Field
              label="Filter Wheel"
              value={`${rig.filter_wheel_name} — ${rig.filter_wheel_positions} positions`}
            />
          )}
          {rig.single_filter_id && (
            <Field label="Single Filter" value={rig.single_filter_name ?? ""} />
          )}
          {rig.filter_slots.length > 0 && (
            <Box sx={{ mt: 1 }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: "block", mb: 0.5 }}
              >
                Slots:
              </Typography>
              <Box
                component="table"
                sx={{
                  borderCollapse: "collapse",
                  "& td, & th": {
                    py: 0.3,
                    px: 1,
                    textAlign: "left",
                    fontSize: "0.875rem",
                  },
                  "& th": { color: "text.secondary", fontWeight: 500 },
                }}
              >
                <thead>
                  <tr>
                    <th>Slot</th>
                    <th>Filter</th>
                    <th>Type</th>
                    <th>Passbands</th>
                  </tr>
                </thead>
                <tbody>
                  {rig.filter_slots.map((s) => (
                    <tr key={s.slot_number}>
                      <td>{s.slot_number}</td>
                      <td>{s.filter_name}</td>
                      <td>{s.filter_type_name}</td>
                      <td>{s.passbands.join(", ") || "\u2014"}</td>
                    </tr>
                  ))}
                </tbody>
              </Box>
            </Box>
          )}
        </DetailSection>
      )}

      {(rig.oag_id || rig.guide_scope_id || rig.guide_camera_id) && (
        <DetailSection title="Guiding">
          {rig.oag_id && <Field label="OAG" value={rig.oag_name ?? ""} />}
          {rig.guide_scope_id && (
            <Field
              label="Guide Scope"
              value={`${rig.guide_scope_name}${
                rig.guide_scope_focal_length_mm
                  ? ` — ${rig.guide_scope_focal_length_mm}mm`
                  : ""
              }`}
            />
          )}
          {rig.guide_camera_id && (
            <Field label="Guide Camera" value={rig.guide_camera_name ?? ""} />
          )}
        </DetailSection>
      )}

      {rig.mount_id && (
        <DetailSection title="Mount">
          <Field label="Mount" value={rig.mount_name ?? ""} />
        </DetailSection>
      )}

      {(rig.focuser_id || rig.computer_id || rig.software.length > 0) && (
        <DetailSection title="Accessories">
          {rig.focuser_id && (
            <Field label="Focuser" value={rig.focuser_name ?? ""} />
          )}
          {rig.computer_id && (
            <Field label="Computer" value={rig.computer_name ?? ""} />
          )}
          {rig.software.length > 0 && (
            <Field
              label="Software"
              value={rig.software.map((s) => s.name).join(", ")}
            />
          )}
        </DetailSection>
      )}

      {rig.notes && (
        <DetailSection title="Notes">
          <Typography
            variant="body2"
            sx={{ whiteSpace: "pre-wrap", color: "text.secondary" }}
          >
            {rig.notes}
          </Typography>
        </DetailSection>
      )}
    </Box>
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Box>
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
        {title}
      </Typography>
      <Box sx={{ pl: 1 }}>{children}</Box>
    </Box>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <Box sx={{ display: "flex", gap: 1, mb: 0.25 }}>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ minWidth: 140, flexShrink: 0 }}
      >
        {label}:
      </Typography>
      <Typography variant="body2">{value}</Typography>
    </Box>
  );
}
