import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CircularProgress from "@mui/material/CircularProgress";
import CloseIcon from "@mui/icons-material/Close";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import ImageOutlinedIcon from "@mui/icons-material/ImageOutlined";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import StarIcon from "@mui/icons-material/Star";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import { useState } from "react";
import { fetchDso } from "@/api/dsos";
import DsoDistanceHelpDialog from "@/components/dso/DsoDistanceHelpDialog";
import SkyPreview from "@/components/dso/SkyPreview";
import { displayConstellation } from "@/lib/constellations";
import { formatDistance, formatDistanceMethod } from "@/lib/distanceFormat";
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

function AugmentedBadge({ tooltip }: { tooltip: string }) {
  return (
    <Tooltip title={tooltip} placement="top">
      <StarIcon
        sx={{
          fontSize: 12,
          color: "primary.main",
          cursor: "help",
        }}
      />
    </Tooltip>
  );
}

function Field({ label, value }: { label: React.ReactNode; value: React.ReactNode }) {
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
  const [distanceHelpOpen, setDistanceHelpOpen] = useState(false);
  const [imagePreviewOpen, setImagePreviewOpen] = useState(false);
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
      PaperProps={{
        sx: {
          // Flex-column so the header stays fixed at the top and the
          // body Box's ``flex: 1 + overflowY: auto`` actually bounds
          // its scroll area to the remaining Paper height. Without
          // this, long content pushes the header out of view and the
          // close button becomes unreachable.
          height: "65vh",
          maxHeight: "65vh",
          display: "flex",
          flexDirection: "column",
        },
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", px: 3, py: 2, borderBottom: 1, borderColor: "divider", flexShrink: 0 }}>
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
                <Stack direction="row" alignItems="center" gap={0.75} sx={{ mt: 0.5 }}>
                  <Typography variant="subtitle1" color="text.secondary">
                    {data.common_name}
                  </Typography>
                  {data.common_name_augmented && (
                    <AugmentedBadge tooltip="Refined by NightCrate editorial data" />
                  )}
                </Stack>
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
          <Stack
            direction={{ xs: "column", md: "row-reverse" }}
            spacing={3}
            alignItems="flex-start"
          >
            {/* DSS2 preview — sits top-right on desktop (row-reverse
                puts the image column second in DOM but first visually
                on the right) and above the metadata on mobile. Uses
                the same ``detail`` variant + 800×800 source as the
                Planner's detail hero, so the disk-cached tile is
                shared between the two views even though this view
                displays it at a smaller CSS size. The explicit
                no-coords branch covers DSOs with NULL RA/Dec (no
                DSS2 tile can exist without a sky position). */}
            {dsoId != null && (
              <Box
                sx={{
                  width: { xs: "100%", md: 340 },
                  maxWidth: { xs: 340, md: 340 },
                  mx: { xs: "auto", md: 0 },
                  aspectRatio: "1 / 1",
                  flexShrink: 0,
                  borderRadius: 1,
                  overflow: "hidden",
                  border: 1,
                  borderColor: "divider",
                  // Desktop: pin to top of the scrolling body so the
                  // preview stays visible while the metadata column
                  // scrolls past it. Mobile reverts to inline because
                  // sticky is noisy when the image itself takes up
                  // most of the narrow viewport.
                  position: { xs: "relative", md: "sticky" },
                  top: { xs: "auto", md: 0 },
                  alignSelf: { md: "flex-start" },
                }}
              >
                {data.ra_deg != null && data.dec_deg != null ? (
                  <>
                    <SkyPreview
                      raDeg={data.ra_deg}
                      decDeg={data.dec_deg}
                      majAxisArcmin={data.maj_axis_arcmin ?? null}
                      size={340}
                    />
                    <Tooltip title="View full image" placement="left">
                      <IconButton
                        size="small"
                        onClick={() => setImagePreviewOpen(true)}
                        sx={{
                          position: "absolute",
                          top: 6,
                          right: 6,
                          // Translucent pill that reads on any sky
                          // backdrop without dominating the tile. A
                          // darker hover adds the affordance cue.
                          bgcolor: "rgba(0, 0, 0, 0.55)",
                          color: "#ffffff",
                          "&:hover": { bgcolor: "rgba(0, 0, 0, 0.75)" },
                        }}
                        aria-label="View full image"
                      >
                        <OpenInFullIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </>
                ) : (
                  <Stack
                    direction="column"
                    alignItems="center"
                    justifyContent="center"
                    gap={1}
                    sx={{
                      position: "absolute",
                      inset: 0,
                      bgcolor: "action.hover",
                      color: "text.secondary",
                    }}
                  >
                    <ImageOutlinedIcon sx={{ fontSize: 48 }} />
                    <Typography variant="body2">
                      No image available
                    </Typography>
                    <Typography variant="caption" color="text.disabled">
                      Object has no coordinates on record
                    </Typography>
                  </Stack>
                )}
              </Box>
            )}
            <Box
              sx={{
                flex: 1,
                minWidth: 0,
                // Responsive metadata layout:
                //   xs/sm: image inline + metadata single column (natural flow)
                //   md:    image sticky top-right + single-column metadata
                //   lg+:   image sticky top-right + two-column metadata
                // CSS multi-column keeps section order stable and
                // rebalances automatically as the viewport resizes.
                columnCount: { xs: 1, lg: 2 },
                columnGap: 3,
                "& > *": {
                  breakInside: "avoid",
                  // ``mb`` replaces the previous Stack ``spacing={3}``
                  // so sections stay separated without relying on
                  // flex gap (which doesn't apply inside CSS columns).
                  mb: 3,
                },
                "& > *:last-child": { mb: 0 },
              }}
            >
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
              <Field
                label={
                  <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                    B (blue) magnitude
                    <Tooltip
                      title={
                        "\u2248 photographic magnitude (Johnson B is modern CCD photometry; " +
                        "historical mpg values differ by ~0.1\u20130.3 mag)."
                      }
                      placement="top"
                    >
                      <HelpOutlineIcon
                        sx={{ fontSize: 14, color: "text.disabled", cursor: "help" }}
                      />
                    </Tooltip>
                  </Box>
                }
                value={formatMagnitude(data.mag_b)}
              />
              <Field
                label="J / H / K"
                value={
                  data.mag_j != null || data.mag_h != null || data.mag_k != null
                    ? `${formatMagnitude(data.mag_j)} / ${formatMagnitude(data.mag_h)} / ${formatMagnitude(data.mag_k)}`
                    : "—"
                }
              />
              <Field
                label="Surface brightness"
                value={
                  data.surface_brightness != null ? (
                    <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
                      {data.surface_brightness.toFixed(2)} mag/arcsec²
                      {data.surface_brightness_augmented && (
                        <AugmentedBadge
                          tooltip="Added by NightCrate editorial data (OpenNGC doesn't provide surface brightness for non-galaxy objects)"
                        />
                      )}
                    </Box>
                  ) : (
                    "—"
                  )
                }
              />
              {data.distance_pc != null && (
                <Field
                  label={
                    <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                      Distance
                      <Tooltip title="How distances are computed" placement="top">
                        <IconButton
                          size="small"
                          onClick={() => setDistanceHelpOpen(true)}
                          sx={{ p: 0 }}
                          aria-label="distance help"
                        >
                          <HelpOutlineIcon
                            sx={{ fontSize: 14, color: "text.disabled" }}
                          />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  }
                  value={
                    <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
                      {data.distance_method === "redshift" ? "~" : ""}
                      {formatDistance(data.distance_pc)?.compact}
                      <Chip
                        label={formatDistanceMethod(data.distance_method)}
                        size="small"
                        variant="outlined"
                        sx={{ height: 18, fontSize: "0.65rem" }}
                      />
                    </Box>
                  }
                />
              )}
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

            <Box
              sx={{
                pt: 2,
                borderTop: 1,
                borderColor: "divider",
              }}
            >
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
            </Box>
          </Stack>
        )}
      </Box>
      <DsoDistanceHelpDialog
        open={distanceHelpOpen}
        onClose={() => setDistanceHelpOpen(false)}
      />

      {/* Full-size image preview. Reuses the same ``detail`` variant
          the tile already fetched — the 800×800 JPEG is already on
          disk, so opening this modal is instant on the second click. */}
      <Dialog
        open={imagePreviewOpen}
        onClose={() => setImagePreviewOpen(false)}
        maxWidth={false}
        PaperProps={{
          sx: {
            // Sized to fit an 800×800 tile plus a thin border. Lets
            // the dialog shrink on smaller viewports without
            // upscaling the tile past its native resolution.
            m: 2,
            bgcolor: "background.paper",
          },
        }}
      >
        <DialogContent sx={{ p: 0, position: "relative" }}>
          {data != null && data.ra_deg != null && data.dec_deg != null && (
            <Box
              sx={{
                // Full-size preview container. Same auto-tier decision
                // as the 340 px thumbnail, just rendered at a larger
                // CSS size — cells resolve from the same cache.
                width: { xs: "min(90vw, 800px)", sm: "min(85vh, 800px)" },
                maxWidth: 800,
                aspectRatio: "1 / 1",
                position: "relative",
                bgcolor: "#000000",
              }}
            >
              <SkyPreview
                raDeg={data.ra_deg}
                decDeg={data.dec_deg}
                majAxisArcmin={data.maj_axis_arcmin ?? null}
                size={800}
              />
            </Box>
          )}
          <IconButton
            size="small"
            onClick={() => setImagePreviewOpen(false)}
            sx={{
              position: "absolute",
              top: 8,
              right: 8,
              bgcolor: "rgba(0, 0, 0, 0.55)",
              color: "#ffffff",
              "&:hover": { bgcolor: "rgba(0, 0, 0, 0.75)" },
            }}
            aria-label="Close preview"
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogContent>
      </Dialog>
    </Drawer>
  );
}
