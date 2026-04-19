import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CircularProgress from "@mui/material/CircularProgress";
import CloseIcon from "@mui/icons-material/Close";
import { fetchDso } from "@/api/dsos";
import { displayConstellation } from "@/lib/constellations";
import { displayDsoType, dsoTypeColor } from "@/lib/dsoTypeNames";
import {
  formatDec,
  formatMagnitude,
  formatRa,
  formatSize,
} from "@/lib/dsoFormatters";

interface Props {
  dsoId: number | null;
  onClose: () => void;
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === "" || value === "—") return null;
  return (
    <Box sx={{ display: "flex", gap: 2, py: 0.5 }}>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ minWidth: 160, flexShrink: 0 }}
      >
        {label}
      </Typography>
      <Typography variant="body2" sx={{ flex: 1 }}>
        {value}
      </Typography>
    </Box>
  );
}

export default function DsoDetailPanel({ dsoId, onClose }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["dso", dsoId],
    queryFn: () => fetchDso(dsoId!),
    enabled: dsoId != null,
  });

  return (
    <Drawer
      anchor="bottom"
      open={dsoId != null}
      onClose={onClose}
      PaperProps={{ sx: { height: "65vh", maxHeight: "65vh" } }}
    >
      <Box sx={{ display: "flex", alignItems: "center", px: 3, py: 2, borderBottom: 1, borderColor: "divider" }}>
        <Box sx={{ flex: 1 }}>
          {data && (
            <>
              <Stack direction="row" gap={2} alignItems="baseline">
                <Typography variant="h5" fontWeight={600}>
                  {data.primary_designation}
                </Typography>
                <Chip
                  label={displayDsoType(data.obj_type)}
                  size="small"
                  sx={{
                    bgcolor: dsoTypeColor(data.obj_type),
                    color: "#ffffff",
                    fontWeight: 500,
                  }}
                />
                {data.constellation && (
                  <Typography variant="body2" color="text.secondary">
                    {displayConstellation(data.constellation)}
                  </Typography>
                )}
              </Stack>
              {data.common_name && (
                <Typography variant="subtitle1" color="text.secondary" sx={{ mt: 0.5 }}>
                  {data.common_name}
                </Typography>
              )}
            </>
          )}
        </Box>
        <IconButton onClick={onClose} size="small">
          <CloseIcon />
        </IconButton>
      </Box>

      <Box sx={{ flex: 1, overflowY: "auto", px: 3, py: 2 }}>
        {isLoading && <CircularProgress />}
        {data && (
          <Stack spacing={3}>
            <Box>
              <Typography variant="overline" color="text.secondary">
                Coordinates
              </Typography>
              <Field label="Right ascension" value={formatRa(data.ra_deg)} />
              <Field label="Declination" value={formatDec(data.dec_deg)} />
              <Field
                label="Decimal (J2000)"
                value={
                  data.ra_deg != null && data.dec_deg != null
                    ? `${data.ra_deg.toFixed(5)}°, ${data.dec_deg.toFixed(5)}°`
                    : "—"
                }
              />
            </Box>

            <Box>
              <Typography variant="overline" color="text.secondary">
                Apparent size & photometry
              </Typography>
              <Field label="Size" value={formatSize(data.maj_axis_arcmin, data.min_axis_arcmin)} />
              <Field
                label="Position angle"
                value={data.position_angle_deg != null ? `${data.position_angle_deg.toFixed(0)}°` : "—"}
              />
              <Field label="V (visual) magnitude" value={formatMagnitude(data.mag_v)} />
              <Field label="B (blue) magnitude" value={formatMagnitude(data.mag_b)} />
              <Field label="J / H / K" value={
                data.mag_j != null || data.mag_h != null || data.mag_k != null
                  ? `${formatMagnitude(data.mag_j)} / ${formatMagnitude(data.mag_h)} / ${formatMagnitude(data.mag_k)}`
                  : "—"
              } />
              <Field
                label="Surface brightness"
                value={data.surface_brightness != null ? `${data.surface_brightness.toFixed(2)} mag/arcsec²` : "—"}
              />
            </Box>

            <Box>
              <Typography variant="overline" color="text.secondary">
                Designations ({data.designations.length})
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mt: 1 }}>
                {data.designations.map((d) => (
                  <Chip
                    key={`${d.catalog}-${d.identifier}`}
                    label={d.display_form}
                    size="small"
                    variant={d.is_primary ? "filled" : "outlined"}
                    color={d.is_primary ? "primary" : "default"}
                  />
                ))}
              </Stack>
            </Box>

            {(data.hubble_type || data.redshift != null || data.radial_velocity != null ||
              data.pm_ra != null || data.pm_dec != null) && (
              <Box>
                <Typography variant="overline" color="text.secondary">
                  Morphology & kinematics
                </Typography>
                <Field label="Hubble type" value={data.hubble_type} />
                <Field label="Redshift (z)" value={data.redshift != null ? data.redshift.toFixed(6) : null} />
                <Field
                  label="Radial velocity"
                  value={data.radial_velocity != null ? `${data.radial_velocity.toFixed(0)} km/s` : null}
                />
                <Field
                  label="Proper motion (RA, Dec)"
                  value={
                    data.pm_ra != null || data.pm_dec != null
                      ? `${data.pm_ra ?? "—"}, ${data.pm_dec ?? "—"} mas/yr`
                      : null
                  }
                />
              </Box>
            )}

            {data.cstar_id && (
              <Box>
                <Typography variant="overline" color="text.secondary">
                  Central star
                </Typography>
                <Field label="Identifier" value={data.cstar_id} />
                <Field label="U / B / V" value={
                  data.cstar_mag_u != null || data.cstar_mag_b != null || data.cstar_mag_v != null
                    ? `${formatMagnitude(data.cstar_mag_u)} / ${formatMagnitude(data.cstar_mag_b)} / ${formatMagnitude(data.cstar_mag_v)}`
                    : "—"
                } />
              </Box>
            )}

            {(data.openngc_notes || data.ned_notes) && (
              <Box>
                <Typography variant="overline" color="text.secondary">
                  Notes
                </Typography>
                {data.openngc_notes && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    {data.openngc_notes}
                  </Typography>
                )}
                {data.ned_notes && (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    {data.ned_notes}
                  </Typography>
                )}
              </Box>
            )}

            <Divider />
            <Box>
              <Typography variant="caption" color="text.secondary">
                Source: {data.source.display_name}
                {data.source.version ? ` · ${data.source.version}` : ""}
                {data.source.license ? ` · ${data.source.license}` : ""}
                {data.source.source_url && (
                  <>
                    {" · "}
                    <Link href={data.source.source_url} target="_blank" rel="noopener noreferrer">
                      upstream
                    </Link>
                  </>
                )}
              </Typography>
            </Box>
          </Stack>
        )}
      </Box>
    </Drawer>
  );
}
