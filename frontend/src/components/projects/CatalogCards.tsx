import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import EditNoteIcon from "@mui/icons-material/EditNote";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import { memo } from "react";
import {
  catalogThumbnailUrl,
  masterThumbnailUrl,
  type CatalogFrame,
  type CatalogMaster,
  type CatalogOther,
} from "@/api/projectCatalog";

// ── formatters ────────────────────────────────────────────────────────────────

export function formatDate(iso: string | null, tz: string): string {
  if (!iso) return "";
  // FITS DATE-OBS is UTC; if the stored string carries no tz, treat it as UTC.
  const hasTz = /[zZ]$|[+-]\d\d:?\d\d$/.test(iso);
  const d = new Date(hasTz ? iso : `${iso}Z`);
  if (isNaN(d.getTime())) return iso;
  try {
    // Explicit components (not dateStyle/timeStyle) so timeZoneName is allowed —
    // every timestamp carries its zone, e.g. "Jun 20, 2026, 8:55 PM MST".
    return new Intl.DateTimeFormat(undefined, {
      timeZone: tz,
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    }).format(d);
  } catch {
    return d.toISOString();
  }
}

export function formatExposure(sec: number | null): string {
  if (sec == null) return "";
  if (sec < 60) return `${sec < 10 ? sec.toFixed(1) : Math.round(sec)}s`;
  const m = sec / 60;
  if (m < 60) return `${m.toFixed(1)}m`;
  return `${Math.floor(m / 60)}h ${Math.round(m % 60)}m`;
}

/** Single sub-frame exposure — astrophotographers quote these in seconds. */
export function formatSubExposure(sec: number | null): string {
  if (sec == null) return "";
  return sec < 10 ? `${sec.toFixed(1)}s` : `${Math.round(sec)}s`;
}

export function formatSize(bytes: number | null): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function splitFile(full: string | null): { name: string; dir: string } {
  if (!full) return { name: "", dir: "" };
  const i = full.lastIndexOf("/");
  return {
    name: i >= 0 ? full.slice(i + 1) : full,
    dir: i >= 0 ? full.slice(0, i) : "",
  };
}

function dims(w: number | null, h: number | null): string | null {
  return w && h ? `${w}×${h}` : null;
}

function joinDot(parts: (string | null | undefined)[]): string {
  return parts.filter(Boolean).join("  ·  ");
}

// ── shared bits ───────────────────────────────────────────────────────────────

const ELLIPSIS = {
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
} as const;

// Left-to-right mark — keeps a path reading correctly inside the rtl box used to
// truncate it from the start.
const LRM = "\u200e";

/** Selection checkbox that reports whether shift was held, for range selects.
 *
 *  onChange's event carries the modifier on its nativeEvent; reading it there
 *  rather than adding a separate onClick keeps a single source of truth for the
 *  click. `userSelect: none` stops shift-click from highlighting card text. */
function SelectBox({
  checked,
  onToggle,
  id,
  label,
}: {
  checked: boolean;
  onToggle: (id: number, shift: boolean) => void;
  id: number;
  label: string;
}) {
  return (
    <Checkbox
      size="small"
      checked={checked}
      onChange={(e) => onToggle(id, (e.nativeEvent as MouseEvent).shiftKey === true)}
      inputProps={{ "aria-label": `select ${label}` }}
      sx={{ alignSelf: "flex-start", p: 0.5, userSelect: "none" }}
    />
  );
}

function Thumb({ src }: { src: string }) {
  return (
    <Box
      component="img"
      src={src}
      alt=""
      loading="lazy"
      sx={{
        width: 84,
        height: 84,
        flexShrink: 0,
        objectFit: "cover",
        borderRadius: 1,
        bgcolor: "action.hover",
      }}
      onError={(e) => {
        (e.currentTarget as HTMLImageElement).style.visibility = "hidden";
      }}
    />
  );
}

function FileNameBlock({ path }: { path: string | null }) {
  const { name, dir } = splitFile(path);
  return (
    <Tooltip title={path ?? ""}>
      <Box sx={{ minWidth: 0 }}>
        <Typography
          sx={{ fontFamily: "monospace", fontWeight: 600, fontSize: 13, ...ELLIPSIS }}
        >
          {name}
        </Typography>
        {dir && (
          <Box
            sx={{
              fontFamily: "monospace",
              fontSize: 11,
              color: "text.secondary",
              overflow: "hidden",
              whiteSpace: "nowrap",
              textOverflow: "ellipsis",
              // Full path; when it overflows, clip from the START so the
              // meaningful tail (…/raw/H) stays visible. The LRM keeps the
              // path reading left-to-right inside the rtl box.
              direction: "rtl",
              textAlign: "left",
            }}
          >
            {LRM + dir}
          </Box>
        )}
      </Box>
    </Tooltip>
  );
}

function StatText({ children }: { children: React.ReactNode }) {
  return (
    <Typography sx={{ fontSize: 12.5, color: "text.secondary", ...ELLIPSIS }}>
      {children}
    </Typography>
  );
}

/** "196 / 4,095" when the camera's ADC range is known, else "196".
 *
 *  A bare ADU figure can't be judged on its own — the same 30,000 is about half
 *  scale on a 16-bit body and off the end of a 12-bit one, and a 12-bit camera
 *  still writes into a 16-bit file, so the number alone gives no clue. */
function aduPair(value: number, fullScale: number | null): string {
  const v = Math.round(value).toLocaleString();
  return fullScale ? `${v} / ${fullScale.toLocaleString()} ADU` : `${v} ADU`;
}

/** Slate blue in both themes — sets the measured numbers apart from the
 *  header-derived capture settings without reaching for red or green. */
const QUALITY_COLOR = "secondary.main";

/** One `Label: value` row. The label carries the tooltip; only it is help-cursored. */
function QualityStat({
  label,
  value,
  help,
}: {
  label: string;
  value: string;
  help: string;
}) {
  return (
    <>
      <Tooltip title={help} placement="left">
        <Typography
          component="span"
          sx={{
            fontSize: 12.5,
            color: QUALITY_COLOR,
            opacity: 0.85,
            cursor: "help",
            whiteSpace: "nowrap",
          }}
        >
          {label}:
        </Typography>
      </Tooltip>
      <Typography
        component="span"
        sx={{
          fontSize: 12.5,
          color: QUALITY_COLOR,
          fontWeight: 500,
          whiteSpace: "nowrap",
          textAlign: "right",
        }}
      >
        {value}
      </Typography>
    </>
  );
}

/**
 * Measured quality as a second column beside the capture settings.
 *
 * Renders nothing at all when unanalyzed — a column of dashes on thousands of
 * cards is noise. Lights get the star metrics; calibration frames get the level
 * readings only, which is the whole point of measuring them (flat exposure,
 * dark pedestal). `median` is dropped for lights because on a sky-dominated
 * frame it lands within a fraction of a percent of the background.
 */
function QualityColumn({ row }: { row: CatalogFrame }) {
  if (!row.quality_analyzed_at) return null;

  if (row.quality_status === "unreadable") {
    return (
      <Tooltip title="This file could not be read the last time quality was measured — the volume was probably offline. Re-run the analysis to try again.">
        <Typography sx={{ fontSize: 12.5, color: "text.disabled", cursor: "help" }}>
          Quality: unreadable
        </Typography>
      </Tooltip>
    );
  }

  const hasStars = row.star_count != null;
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "auto auto",
        columnGap: 1,
        rowGap: 0.125,
        alignContent: "start",
      }}
    >
      {row.hfr != null && (
        <QualityStat
          label="HFR"
          // Both figures: pixels is what was measured, arcseconds is what is
          // comparable between rigs. Arcsec is omitted rather than guessed when
          // the frame's folder has no rig tagged.
          value={
            row.hfr_arcsec != null
              ? `${row.hfr.toFixed(2)} px \u00b7 ${row.hfr_arcsec.toFixed(2)}\u2033`
              : `${row.hfr.toFixed(2)} px`
          }
          help={
            row.hfr_arcsec != null
              ? `Half-Flux Radius — the median over every detected star. Lower is sharper. Shown in arcseconds (${row.hfr.toFixed(2)} px at ${row.pixel_scale_arcsec?.toFixed(3)}"/px, from the rig tagged on this frame's source folder), which is comparable between rigs.`
              : "Half-Flux Radius — the median over every detected star, in pixels. Lower is sharper. Tag this frame's source folder with a rig and this becomes arcseconds, which is comparable between rigs — a pixel subtends a different angle on each scope."
          }
        />
      )}
      {row.star_count != null && (
        <QualityStat
          label="Stars"
          value={row.star_count.toLocaleString()}
          help="Stars detected using fixed settings, so counts are comparable between frames. Well below the rest of the night usually means cloud, dew or lost focus. Not comparable across PixInsight processing stages — detection is sensitive to the noise floor."
        />
      )}
      {row.snr_estimate != null && (
        <QualityStat
          label="Star SNR"
          value={row.snr_estimate.toFixed(0)}
          help="Median signal-to-noise of the detected stars — mainly a transparency indicator. This is not the Statistics panel's median/σ, which measures the sky against its own noise."
        />
      )}
      {!hasStars && row.median_adu != null && (
        <QualityStat
          label="Median"
          value={aduPair(row.median_adu, row.full_scale_adu)}
          help={
            "Median pixel level in raw ADU, against the camera's full scale (2^ADC - 1). " +
            (row.full_scale_adu && row.median_adu
              ? `That is ${((row.median_adu / row.full_scale_adu) * 100).toFixed(1)}% of full scale. `
              : "Tag this frame's source folder with a rig to see the full-scale figure. ") +
            "On a flat this is the exposure check — around a third to a half of full scale is the usual aim. On a dark or bias it is the offset pedestal."
          }
        />
      )}
      {row.background_adu != null && (
        <QualityStat
          label="Sky"
          value={aduPair(row.background_adu, row.full_scale_adu)}
          help={
            "Sky background in raw ADU, against the camera's full scale. " +
            (row.full_scale_adu && row.background_adu
              ? `That is ${((row.background_adu / row.full_scale_adu) * 100).toFixed(1)}% of full scale. `
              : "") +
            "Rises with moonlight, twilight and light pollution. PixInsight float files carry no bit depth, so theirs is normalized \u00d7 65535 rather than a real sensor reading."
          }
        />
      )}
      {row.quality_status === "no_stars" && (
        <Tooltip title="The file read fine but detection found nothing — cloud, a closed shutter, or badly defocused. A real result, not an error.">
          <Typography
            sx={{ gridColumn: "1 / -1", fontSize: 12.5, color: "text.disabled", cursor: "help" }}
          >
            no stars found
          </Typography>
        </Tooltip>
      )}
    </Box>
  );
}

const CARD_SX = {
  p: 1.5,
  display: "flex",
  gap: 1.5,
  height: "100%",
  alignItems: "flex-start",
} as const;

// ── cards ─────────────────────────────────────────────────────────────────────

/** Filter chip — the FITS FILTER header value, which is the only filter fact a
 * cataloged frame carries (there is no equipment identification). */
function FilterChip({ row }: { row: CatalogFrame }) {
  if (!row.filter_name) return null;
  return (
    <Tooltip title={`FILTER header: ${row.filter_name}`}>
      <Chip size="small" variant="outlined" color="primary" label={row.filter_name} />
    </Tooltip>
  );
}

/** Rig chip — inherited from the source folder the user tagged, so it is a
 * declared fact rather than anything read out of a header. Absent when the
 * folder carries no rig, which is a valid state ("not stated"). */
function RigChip({ row }: { row: CatalogFrame }) {
  if (!row.rig_name) return null;
  return <Chip size="small" variant="outlined" label={row.rig_name} />;
}

// Memoized: the catalog is an infinite-scroll list that can hold thousands of
// cards, and opening/closing the corrections dialog re-renders the whole tab.
// `row` identity is stable from the query cache and `onCorrect` / `onOpen` are
// stable setters, so memo makes that toggle O(1) instead of O(loaded cards).
function FrameCardImpl({
  row,
  projectId,
  tz,
  showFilter,
  showObject,
  onCorrect,
  onOpen,
  selected = false,
  onToggleSelect,
}: {
  row: CatalogFrame;
  projectId: number;
  tz: string;
  showFilter: boolean;
  showObject: boolean;
  onCorrect?: (row: CatalogFrame) => void;
  onOpen?: (row: CatalogFrame) => void;
  // Primitives, not objects, so the memo above still holds when the selection changes.
  selected?: boolean;
  onToggleSelect?: (id: number, shift: boolean) => void;
}) {
  const capture = joinDot([
    formatSubExposure(row.exposure_seconds) || null,
    row.gain != null ? `gain ${row.gain}` : null,
    row.set_temp_c != null ? `${row.set_temp_c}°C` : null,
    row.binning ? row.binning.replace("x", "×") : null,
  ]);
  const sizeLine = joinDot([
    dims(row.image_width, row.image_height),
    formatSize(row.file_size_bytes) || null,
  ]);
  return (
    <Paper
      variant="outlined"
      sx={{
        ...CARD_SX,
        ...(selected ? { borderColor: "primary.main", bgcolor: "action.selected" } : null),
      }}
    >
      {onToggleSelect && (
        <SelectBox
          checked={selected}
          onToggle={onToggleSelect}
          id={row.id}
          label={row.path ?? String(row.id)}
        />
      )}
      <Thumb src={catalogThumbnailUrl(projectId, row.id)} />
      <Box sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 0.25 }}>
        <FileNameBlock path={row.path} />
        {(showFilter || showObject || row.rig_name) && (
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1,
              mt: 0.25,
              minWidth: 0,
              flexWrap: "wrap",
            }}
          >
            {showFilter && <FilterChip row={row} />}
            <RigChip row={row} />
            {showObject && row.object_hint && (
              <Typography sx={{ fontSize: 13, ...ELLIPSIS }}>{row.object_hint}</Typography>
            )}
          </Box>
        )}
        {/* Header-derived capture settings on the left, measured quality on the
            right — two columns so the measured numbers read as a separate kind
            of fact rather than more of the same line. */}
        <Box sx={{ display: "flex", gap: 3, minWidth: 0, alignItems: "flex-start" }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            {capture && <StatText>{capture}</StatText>}
            {sizeLine && <StatText>{sizeLine}</StatText>}
            <Typography sx={{ fontSize: 11, color: "text.secondary", mt: 0.25 }}>
              {formatDate(row.date_obs_utc, tz)}
            </Typography>
          </Box>
          <QualityColumn row={row} />
        </Box>
      </Box>
      <Box sx={{ display: "flex", alignSelf: "flex-start", ml: "auto" }}>
        {onOpen && row.path && (
          <Tooltip title="Open in the Image Analyzer">
            <IconButton
              size="small"
              aria-label="open in image analyzer"
              onClick={() => onOpen(row)}
            >
              <OpenInFullIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
        {onCorrect && (
          <Tooltip title="Classification (frame type / target)">
            <IconButton
              size="small"
              aria-label="correct classification"
              onClick={() => onCorrect(row)}
            >
              <EditNoteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Box>
    </Paper>
  );
}

function MasterCardImpl({
  row,
  projectId,
  tz,
  onOpen,
  selected = false,
  onToggleSelect,
}: {
  row: CatalogMaster;
  projectId: number;
  tz: string;
  onOpen?: (row: CatalogMaster) => void;
  selected?: boolean;
  onToggleSelect?: (id: number, shift: boolean) => void;
}) {
  const integration =
    row.total_exposure_seconds != null
      ? `${formatExposure(row.total_exposure_seconds)} integration`
      : row.ncombine != null
        ? `${row.ncombine} frames`
        : null;
  const sizeLine = joinDot([row.dimensions, formatSize(row.file_size_bytes) || null]);
  return (
    <Paper
      variant="outlined"
      sx={{
        ...CARD_SX,
        ...(selected ? { borderColor: "primary.main", bgcolor: "action.selected" } : null),
      }}
    >
      {onToggleSelect && (
        <SelectBox
          checked={selected}
          onToggle={onToggleSelect}
          id={row.id}
          label={row.path ?? String(row.id)}
        />
      )}
      <Thumb src={masterThumbnailUrl(projectId, row.id)} />
      <Box sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 0.25 }}>
        <FileNameBlock path={row.path} />
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.25, minWidth: 0 }}>
          <Chip size="small" variant="outlined" label={row.type_label} />
          {row.filter_name && (
            <Chip size="small" variant="outlined" color="primary" label={row.filter_name} />
          )}
        </Box>
        {integration && <StatText>{integration}</StatText>}
        {sizeLine && <StatText>{sizeLine}</StatText>}
        <Typography sx={{ fontSize: 11, color: "text.secondary", mt: 0.25 }}>
          {formatDate(row.date_obs_utc, tz)}
        </Typography>
      </Box>
      {onOpen && row.path && (
        <Box sx={{ display: "flex", alignSelf: "flex-start", ml: "auto" }}>
          <Tooltip title="Open in the Image Analyzer">
            <IconButton
              size="small"
              aria-label="open in image analyzer"
              onClick={() => onOpen(row)}
            >
              <OpenInFullIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      )}
    </Paper>
  );
}

function OtherCardImpl({
  row,
  tz,
  projectId,
  selected = false,
  onToggleSelect,
  onCorrect,
}: {
  row: CatalogOther;
  tz: string;
  projectId?: number;
  selected?: boolean;
  onToggleSelect?: (id: number, shift: boolean) => void;
  onCorrect?: (row: CatalogOther) => void;
}) {
  // Only an unknown-type sub frame can be given a frame type. The rest of this
  // tab is PixInsight sidecars, logs and the project file — not frames at all,
  // so they get no checkbox and no edit affordance.
  const correctable = row.kind === "sub_frame";
  return (
    <Paper
      variant="outlined"
      sx={{
        ...CARD_SX,
        ...(selected ? { borderColor: "primary.main", bgcolor: "action.selected" } : null),
      }}
    >
      {onToggleSelect && (
        <SelectBox
          checked={selected}
          onToggle={onToggleSelect}
          id={row.id}
          label={row.path ?? String(row.id)}
        />
      )}
      {/* An unknown-type row is still a real frame with a content hash, so the
          normal frame thumbnail endpoint renders it — seeing the image is how
          you decide what it actually is. */}
      {correctable && projectId != null && (
        <Thumb src={catalogThumbnailUrl(projectId, row.id)} />
      )}
      <Box sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 0.25 }}>
        <Box sx={{ mb: 0.25 }}>
          <Chip size="small" variant="outlined" label={row.type_label} />
        </Box>
        <FileNameBlock path={row.path} />
        <StatText>
          {joinDot([formatSize(row.size_bytes) || null, formatDate(row.date, tz) || null])}
        </StatText>
      </Box>
      {correctable && onCorrect && (
        <Box sx={{ display: "flex", alignSelf: "flex-start", ml: "auto" }}>
          <Tooltip title="Set this frame's type">
            <IconButton
              size="small"
              aria-label="set frame type"
              onClick={() => onCorrect(row)}
            >
              <EditNoteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      )}
    </Paper>
  );
}

export const FrameCard = memo(FrameCardImpl);
export const MasterCard = memo(MasterCardImpl);
export const OtherCard = memo(OtherCardImpl);
