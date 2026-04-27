/**
 * One result card in the Target Planner list.
 *
 * Replaces the old MUI DataGrid row. Layout (horizontal, left → right):
 *   1. DSS2 thumbnail (``ThumbnailCell`` variant "list"), ~96 px square.
 *   2. Rig-framed thumbnail (``ThumbnailCell`` variant "rig_framed")
 *      with the rig's sensor aspect ratio — rendered only when a rig
 *      is selected. Coverage % captioned under it.
 *   3. Info block — three rows:
 *        · Designation (bold) + Common name (muted) + Type pill +
 *          Constellation.
 *        · Size · Mag V · Distance.
 *        · Now-status icon + Hours visible + Meridian / Max-alt +
 *          Moon sep. Hidden entirely in Anytime mode.
 *
 * The whole card is a ``CardActionArea`` so clicking anywhere fires
 * ``onClick`` — matches the grid's row-click → open-detail-panel
 * semantics. The meridian/max-alt collapse logic mirrors what the
 * grid's ``renderCell`` did so behaviour is unchanged across the
 * swap.
 */
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import CircleIcon from "@mui/icons-material/Circle";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import StarIcon from "@mui/icons-material/Star";
import StarBorderIcon from "@mui/icons-material/StarBorder";
import type { PlannerTargetItem } from "@/api/planner";
import { displayConstellation } from "@/lib/constellations";
import { formatDistance } from "@/lib/distanceFormat";
import { formatDec, formatRa } from "@/lib/dsoFormatters";
import { displayDsoType, dsoTypeColor } from "@/lib/dsoTypeNames";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";
import { ScoreChip } from "./ScoreChip";
import ThumbnailCell from "./ThumbnailCell";

interface Props {
  item: PlannerTargetItem;
  /** Rig FOV in degrees — needed by the rig-framed thumbnail. When
   *  ``null``, the rig thumbnail and coverage caption are omitted. */
  rigFovMajorDeg: number | null;
  rigFovMinorDeg: number | null;
  /** Timezone for the location (used by the meridian/max-alt
   *  formatter). Defaults to ``"UTC"`` upstream when no location is
   *  selected; in practice the tonight-line is only rendered when
   *  ``restrictTonight`` is ``true``, which requires a location. */
  tz: string;
  /** ``false`` hides the tonight-line entirely (Anytime mode). */
  restrictTonight: boolean;
  onClick: (dsoId: number) => void;
  isFavorite?: boolean;
  onToggleFavorite?: (dsoId: number) => void;
}

function formatLocalTime(iso: string, tz: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: tz,
    });
  } catch {
    return "—";
  }
}

function NowStatusIcon({ status }: { status: "up" | "rising" | "set" | null }) {
  if (status === "up") {
    return (
      <Tooltip title="Above horizon right now" arrow>
        <CircleIcon sx={{ color: RIG_BLUE, fontSize: 14 }} />
      </Tooltip>
    );
  }
  if (status === "rising") {
    return (
      <Tooltip title="Not up yet — rises during tonight" arrow>
        <ArrowUpwardIcon sx={{ color: RIG_ORANGE, fontSize: 18 }} />
      </Tooltip>
    );
  }
  if (status === "set") {
    return (
      <Tooltip title="Already set for tonight" arrow>
        <ArrowDownwardIcon sx={{ color: "text.secondary", fontSize: 18 }} />
      </Tooltip>
    );
  }
  return null;
}

function formatSize(
  maj: number | null,
  min: number | null,
): string | null {
  if (maj == null) return null;
  if (min != null && min !== maj) {
    return `${maj.toFixed(1)}' × ${min.toFixed(1)}'`;
  }
  return `${maj.toFixed(1)}'`;
}

export default function PlannerTargetCard({
  item,
  rigFovMajorDeg,
  rigFovMinorDeg,
  tz,
  restrictTonight,
  onClick,
  isFavorite,
  onToggleFavorite,
}: Props) {
  const rigAspect =
    rigFovMajorDeg != null && rigFovMinorDeg != null && rigFovMinorDeg > 0
      ? rigFovMajorDeg / rigFovMinorDeg
      : null;
  const showRig = rigFovMajorDeg != null && rigFovMinorDeg != null && rigAspect != null;

  const sizeText = formatSize(item.maj_axis_arcmin, item.min_axis_arcmin);
  const distance = formatDistance(item.distance_pc);

  const maxAlt = item.max_altitude_deg;
  const peakT = item.peak_time_utc;
  const transitAlt = item.altitude_at_transit_deg;
  const transitT = item.transit_time_utc;
  const meridianBlock = renderMeridianBlock({ maxAlt, peakT, transitAlt, transitT, tz });

  const hasScore =
    restrictTonight && (item.score_pct !== null || item.score_breakdown !== null);

  return (
    <Card variant="outlined" sx={{ borderRadius: 2, position: "relative" }}>
      {onToggleFavorite && (
        <IconButton
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            onToggleFavorite(item.dso_id);
          }}
          sx={{
            position: "absolute",
            top: 4,
            right: 4,
            zIndex: 1,
            color: isFavorite ? RIG_ORANGE : "text.disabled",
          }}
          aria-label={isFavorite ? "Remove from wishlist" : "Add to wishlist"}
        >
          {isFavorite ? <StarIcon fontSize="small" /> : <StarBorderIcon fontSize="small" />}
        </IconButton>
      )}
      <CardActionArea
        onClick={() => onClick(item.dso_id)}
        sx={{ p: 1.5 }}
      >
        <Stack direction="row" gap={2} alignItems="flex-start">
          {/* DSS2 thumbnail with now-status glyph pinned top-left. */}
          <Box sx={{ position: "relative", flexShrink: 0 }}>
            <ThumbnailCell dsoId={item.dso_id} size={96} />
            {restrictTonight && item.now_status && (
              <Box
                sx={{
                  position: "absolute",
                  top: 2,
                  left: 2,
                  bgcolor: "rgba(0, 0, 0, 0.55)",
                  borderRadius: "50%",
                  width: 22,
                  height: 22,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <NowStatusIcon status={item.now_status} />
              </Box>
            )}
          </Box>

          {/* Rig-framed thumbnail (only when rig selected). */}
          {showRig && (
            <Stack alignItems="center" spacing={0.25} sx={{ flexShrink: 0 }}>
              <ThumbnailCell
                dsoId={item.dso_id}
                size={96}
                variant="rig_framed"
                fovMajorDeg={rigFovMajorDeg!}
                fovMinorDeg={rigFovMinorDeg!}
                aspectRatio={rigAspect!}
              />
              <Typography
                variant="caption"
                color={item.coverage_pct == null ? "text.disabled" : "text.secondary"}
                sx={{ lineHeight: 1, fontWeight: 500 }}
              >
                {item.coverage_pct == null ? "—" : `${item.coverage_pct.toFixed(0)}%`}
              </Typography>
            </Stack>
          )}

          {/* Info block. */}
          <Stack spacing={0.75} sx={{ flex: 1, minWidth: 0 }}>
            {/* Line 1 — name + type pill + constellation. Score chip
                moved to the card's upper-right corner so the
                designation stays the visual anchor of this line. */}
            <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
              <Typography variant="body1" fontWeight={600}>
                {item.primary_designation}
              </Typography>
              {item.common_name && (
                <Typography variant="body2" color="text.secondary">
                  {item.common_name}
                </Typography>
              )}
              <Chip
                label={displayDsoType(item.obj_type)}
                size="small"
                sx={{
                  bgcolor: dsoTypeColor(item.obj_type),
                  color: "#ffffff",
                  fontWeight: 500,
                  height: 20,
                  "& .MuiChip-label": { px: 0.85, fontSize: "0.72rem" },
                }}
              />
              {item.constellation && (
                <Typography variant="caption" color="text.secondary">
                  in {displayConstellation(item.constellation)}
                </Typography>
              )}
            </Stack>

            {/* Alternate designations — ``·``-separated line in muted
                caption color. Primary is already in the bold title so
                we only show the alternates. Hidden when there are none. */}
            {item.designations && item.designations.some((d) => !d.is_primary) && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: -0.25, lineHeight: 1.3 }}
              >
                {item.designations
                  .filter((d) => !d.is_primary)
                  .map((d) => d.display_form)
                  .join(" · ")}
              </Typography>
            )}

            {/* Line 2 — physical properties (always shown). NOTE: no
                container ``color: text.secondary`` here — that'd inherit
                onto both the Fact label AND the Fact value, defeating
                the label-muted / value-default pattern used on Line 3.
                Keep label-colour in the Fact component only. */}
            <Stack
              direction="row"
              gap={2}
              flexWrap="wrap"
              sx={{ fontSize: "0.8rem" }}
            >
              <Fact label="Size" value={sizeText} />
              <Fact
                label="Mag V"
                value={item.mag_v != null ? item.mag_v.toFixed(1) : null}
              />
              <Fact label="Distance" value={distance ? distance.compact : null} />
              <Fact
                label="RA"
                value={item.ra_deg != null ? formatRa(item.ra_deg) : null}
              />
              <Fact
                label="Dec"
                value={item.dec_deg != null ? formatDec(item.dec_deg) : null}
              />
            </Stack>

            {/* Line 3 — tonight-only visibility info. Hidden in
                Anytime mode so cards collapse vertically. */}
            {restrictTonight && (
              <Stack
                direction="row"
                gap={2}
                flexWrap="wrap"
                alignItems="center"
                sx={{ fontSize: "0.8rem" }}
              >
                <Fact
                  label="Hours visible"
                  value={
                    item.hours_visible != null
                      ? `${item.hours_visible.toFixed(1)}h`
                      : null
                  }
                />
                {meridianBlock}
                <Fact
                  label="Moon sep"
                  value={
                    item.min_moon_separation_deg != null
                      ? `${item.min_moon_separation_deg.toFixed(0)}°`
                      : null
                  }
                />
              </Stack>
            )}

            {/* Line 4 — score chip first, Wikipedia link right after
                with a 20 px gap. Extra ``mt`` over the previous line
                gives the score room to breathe. */}
            {(hasScore || (item.wikipedia_url && item.wikipedia_label)) && (
              <Stack
                direction="row"
                alignItems="center"
                gap="20px"
                sx={{ mt: 1 }}
              >
                {hasScore && (
                  <ScoreChip
                    scorePct={item.score_pct}
                    qualityLabel={item.quality_label}
                    gateFailures={item.score_breakdown?.gate_failures}
                    size="small"
                  />
                )}
                {item.wikipedia_url && item.wikipedia_label && (
                  <Link
                    href={item.wikipedia_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    underline="hover"
                    aria-label={`Open Wikipedia article: ${item.wikipedia_label} (opens in new tab)`}
                    sx={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 0.5,
                      fontSize: "0.78rem",
                      fontWeight: 500,
                    }}
                  >
                    Wikipedia: {item.wikipedia_label}
                    <OpenInNewIcon sx={{ fontSize: 13 }} />
                  </Link>
                )}
              </Stack>
            )}
          </Stack>
        </Stack>
      </CardActionArea>
    </Card>
  );
}

/** Inline `LABEL value` pair; renders nothing when value is null. */
function Fact({ label, value }: { label: string; value: string | null }) {
  if (value == null) return null;
  return (
    <Typography variant="body2" sx={{ lineHeight: 1.3 }}>
      <Box
        component="span"
        sx={{
          color: "text.secondary",
          textTransform: "uppercase",
          letterSpacing: 0.4,
          fontSize: "0.65rem",
          mr: 0.75,
        }}
      >
        {label}
      </Box>
      {value}
    </Typography>
  );
}

/** Meridian / max-altitude block — always two separate lines when
 *  the data is available. Keeping them split (even when transit
 *  lands inside astro-dark and the values agree) reads more
 *  consistently across the card list. Returns the Max alt line
 *  alone if the analytical transit wasn't populated (shouldn't
 *  happen in Tonight mode, but defensive). */
function renderMeridianBlock({
  maxAlt,
  peakT,
  transitAlt,
  transitT,
  tz,
}: {
  maxAlt: number | null;
  peakT: string | null;
  transitAlt: number | null;
  transitT: string | null;
  tz: string;
}) {
  if (maxAlt == null || peakT == null) return null;
  return (
    <Stack spacing={0.15} sx={{ display: "inline-flex" }}>
      {transitAlt != null && transitT != null && (
        <Fact
          label="Meridian"
          value={`${transitAlt.toFixed(0)}° @ ${formatLocalTime(transitT, tz)}`}
        />
      )}
      <Fact
        label="Max alt"
        value={`${maxAlt.toFixed(0)}° @ ${formatLocalTime(peakT, tz)}`}
      />
    </Stack>
  );
}
