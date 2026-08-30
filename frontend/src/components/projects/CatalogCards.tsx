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
  onToggleSelect?: (id: number) => void;
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
        <Checkbox
          size="small"
          checked={selected}
          onChange={() => onToggleSelect(row.id)}
          inputProps={{ "aria-label": `select ${row.path ?? row.id}` }}
          sx={{ alignSelf: "flex-start", p: 0.5 }}
        />
      )}
      <Thumb src={catalogThumbnailUrl(projectId, row.id)} />
      <Box sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 0.25 }}>
        <FileNameBlock path={row.path} />
        {(showFilter || showObject) && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.25, minWidth: 0 }}>
            {showFilter && <FilterChip row={row} />}
            {showObject && row.object_hint && (
              <Typography sx={{ fontSize: 13, ...ELLIPSIS }}>{row.object_hint}</Typography>
            )}
          </Box>
        )}
        {capture && <StatText>{capture}</StatText>}
        {sizeLine && <StatText>{sizeLine}</StatText>}
        <Typography sx={{ fontSize: 11, color: "text.secondary", mt: 0.25 }}>
          {formatDate(row.date_obs_utc, tz)}
        </Typography>
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
}: {
  row: CatalogMaster;
  projectId: number;
  tz: string;
}) {
  const integration =
    row.total_exposure_seconds != null
      ? `${formatExposure(row.total_exposure_seconds)} integration`
      : row.ncombine != null
        ? `${row.ncombine} frames`
        : null;
  const sizeLine = joinDot([row.dimensions, formatSize(row.file_size_bytes) || null]);
  return (
    <Paper variant="outlined" sx={CARD_SX}>
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
    </Paper>
  );
}

function OtherCardImpl({
  row,
  tz,
}: {
  row: CatalogOther;
  tz: string;
}) {
  return (
    <Paper variant="outlined" sx={CARD_SX}>
      <Box sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 0.25 }}>
        <Box sx={{ mb: 0.25 }}>
          <Chip size="small" variant="outlined" label={row.type_label} />
        </Box>
        <FileNameBlock path={row.path} />
        <StatText>
          {joinDot([formatSize(row.size_bytes) || null, formatDate(row.date, tz) || null])}
        </StatText>
      </Box>
    </Paper>
  );
}

export const FrameCard = memo(FrameCardImpl);
export const MasterCard = memo(MasterCardImpl);
export const OtherCard = memo(OtherCardImpl);
