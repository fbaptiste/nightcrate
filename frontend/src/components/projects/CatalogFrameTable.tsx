import { memo } from "react";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import EditNoteIcon from "@mui/icons-material/EditNote";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import IconButton from "@mui/material/IconButton";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import {
  catalogThumbnailUrl,
  type CatalogFrame,
  type CatalogSort,
} from "@/api/projectCatalog";
import { formatNight } from "@/lib/localDate";
import { CatalogInfiniteScroller } from "./CatalogCardList";
import { formatDate, formatSubExposure } from "./CatalogCards";
import FilterSwatch from "./FilterSwatch";
import { notRecordedFilter, resolveFilterLabel } from "./filterColors";
import {
  subFrameSelectionKey,
  type CatalogSelectionKey,
} from "./catalogSelection";

const HFR_HELP = "Half-Flux Radius — the median over every detected star. Lower is sharper. Arcseconds are comparable between rigs; pixels are shown when the image scale is unknown.";
const STARS_HELP = "Stars detected using fixed settings, so counts are comparable between frames. Well below the rest of the night usually means cloud, dew or lost focus. Not comparable across PixInsight processing stages — detection is sensitive to the noise floor.";
const SNR_HELP = "Median signal-to-noise of the detected stars — mainly a transparency indicator. This is not the Statistics panel's median/σ, which measures the sky against its own noise.";
const SKY_HELP = "Sky background in raw ADU, against the camera's full scale. It rises with moonlight, twilight and light pollution. PixInsight float files carry no bit depth, so theirs is normalized × 65535 rather than a real sensor reading.";
const MEDIAN_HELP = "Median pixel level in raw ADU, against the camera's full scale (2^ADC - 1). On a flat this is the exposure check — around a third to a half of full scale is the usual aim. On a dark or bias it is the offset pedestal.";
const UNREADABLE_HELP = "This file could not be read the last time quality was measured — the volume was probably offline. Re-run the analysis to try again.";
const NO_STARS_HELP = "The file read fine but detection found nothing — cloud, a closed shutter, or badly defocused. A real result, not an error.";

interface Props {
  rows: CatalogFrame[];
  projectId: number;
  timezone: string;
  sort: CatalogSort;
  calibration: boolean;
  showRig: boolean;
  showTarget: boolean;
  selected: Set<CatalogSelectionKey>;
  onToggleSelect: (key: CatalogSelectionKey, shift: boolean) => void;
  onSort: (sort: CatalogSort) => void;
  onOpen: (row: CatalogFrame) => void;
  onCorrect: (row: CatalogFrame) => void;
  hasMore: boolean;
  fetchingMore: boolean;
  onLoadMore: () => void;
  loading: boolean;
}

function captureDate(value: string | null, timezone: string, withDate: boolean): string {
  if (!value) return "";
  const hasZone = /[zZ]$|[+-]\d\d:?\d\d$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    ...(withDate ? { day: "numeric", month: "short" } : {}),
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date).replace(",", "");
}

function fileName(path: string | null): string {
  return path?.split(/[\\/]/).pop() ?? "";
}

function temperature(value: number | null): string {
  if (value == null) return "";
  return `${String(value).replace("-", "−")}°C`;
}

function aduText(value: number | null): string {
  return value == null ? "" : `${Math.round(value).toLocaleString()} ADU`;
}

function aduTooltip(
  label: "Median" | "Sky background",
  value: number,
  fullScale: number | null,
): string {
  const valueText = Math.round(value).toLocaleString();
  if (label === "Median") {
    const scale = fullScale
      ? `That is ${((value / fullScale) * 100).toFixed(1)}% of the camera's ${fullScale.toLocaleString()} ADU full scale. `
      : "Tag this frame's source folder with a rig to see the full-scale figure. ";
    return `Median pixel level: ${valueText} ADU. ${scale}On a flat this is the exposure check — around a third to a half of full scale is the usual aim. On a dark or bias it is the offset pedestal.`;
  }
  const scale = fullScale
    ? `That is ${((value / fullScale) * 100).toFixed(1)}% of the camera's ${fullScale.toLocaleString()} ADU full scale. `
    : "";
  return `Sky background: ${valueText} ADU. ${scale}It rises with moonlight, twilight and light pollution. PixInsight float files carry no bit depth, so theirs is normalized × 65535 rather than a real sensor reading.`;
}

function nextSort(
  current: CatalogSort,
  descending: CatalogSort,
  ascending: CatalogSort,
): CatalogSort {
  return current === descending ? ascending : descending;
}

function SortHeader({
  label,
  sort,
  active,
  onClick,
  align = "left",
  help,
  width,
}: {
  label: string;
  sort: CatalogSort;
  active: boolean;
  onClick: () => void;
  align?: "left" | "right";
  help?: string;
  width?: number;
}) {
  const descending = sort.endsWith("_desc");
  const ariaSort = active ? (descending ? "descending" : "ascending") : "none";
  const button = (
    <Button
      size="small"
      color="inherit"
      onClick={onClick}
      sx={{
        width: "100%",
        minWidth: 0,
        minHeight: 32,
        p: 0,
        fontSize: "12px",
        justifyContent: align === "right" ? "flex-end" : "flex-start",
      }}
    >
      {label}{active ? (descending ? " ▼" : " ▲") : ""}
    </Button>
  );
  return (
    <TableCell
      align={align}
      aria-sort={ariaSort}
      sx={{ width, whiteSpace: "nowrap" }}
    >
      {help ? <Tooltip title={help}>{button}</Tooltip> : button}
    </TableCell>
  );
}

export default function CatalogFrameTable({
  rows,
  projectId,
  timezone,
  sort,
  calibration,
  showRig,
  showTarget,
  selected,
  onToggleSelect,
  onSort,
  onOpen,
  onCorrect,
  hasMore,
  fetchingMore,
  onLoadMore,
  loading,
}: Props) {
  const timeSorted = sort === "date_desc" || sort === "date";
  const measuredColumns = calibration ? 2 : 4;
  const columnCount = 8 + measuredColumns + 2 + Number(showRig) + Number(showTarget);

  return (
    <CatalogInfiniteScroller
      itemCount={rows.length}
      hasMore={hasMore}
      fetchingMore={fetchingMore}
      onLoadMore={onLoadMore}
      loading={loading}
      emptyMessage="Nothing in this category yet."
    >
      <Table
        stickyHeader
        size="small"
        sx={{
          width: "100%",
          minWidth: 980 + Number(showRig) * 120 + Number(showTarget) * 140,
          tableLayout: "fixed",
          border: 1,
          borderColor: "divider",
          "& th": {
            px: "6px",
            py: "2px",
            color: "text.secondary",
            fontSize: "12px",
            fontWeight: 500,
            whiteSpace: "nowrap",
          },
          "& td": { px: "6px", py: "4px", fontSize: "13px" },
          "& .MuiTableCell-paddingCheckbox": { width: 44, px: "4px", py: 0 },
        }}
      >
        <TableHead>
          <TableRow>
            <TableCell padding="checkbox" />
            <TableCell sx={{ width: 48 }} />
            <SortHeader
              label="Time"
              sort={sort}
              active={timeSorted}
              onClick={() => onSort(nextSort(sort, "date_desc", "date"))}
              width={78}
            />
            <TableCell sx={{ width: 88 }}>Filter</TableCell>
            <TableCell align="right" sx={{ width: 52 }}>Exp</TableCell>
            <TableCell align="right" sx={{ width: 48 }}>Gain</TableCell>
            <TableCell align="right" sx={{ width: 56 }}>Temp</TableCell>
            <TableCell align="right" sx={{ width: 42 }}>Bin</TableCell>
            {calibration ? (
              <>
                <TableCell align="right" sx={{ width: 76 }}>
                  <Tooltip title={MEDIAN_HELP}><Box component="span">Median</Box></Tooltip>
                </TableCell>
                <SortHeader
                  label="Sky"
                  sort={sort}
                  active={sort === "background_desc" || sort === "background_asc"}
                  onClick={() => onSort(nextSort(sort, "background_desc", "background_asc"))}
                  align="right"
                  help={SKY_HELP}
                  width={76}
                />
              </>
            ) : (
              <>
                <SortHeader
                  label="HFR"
                  sort={sort}
                  active={sort === "hfr_arcsec_desc" || sort === "hfr_arcsec_asc"}
                  onClick={() => onSort(nextSort(sort, "hfr_arcsec_desc", "hfr_arcsec_asc"))}
                  align="right"
                  help={HFR_HELP}
                  width={58}
                />
                <SortHeader
                  label="Stars"
                  sort={sort}
                  active={sort === "stars_asc" || sort === "stars_desc"}
                  onClick={() => onSort(nextSort(sort, "stars_asc", "stars_desc"))}
                  align="right"
                  help={STARS_HELP}
                  width={58}
                />
                <TableCell align="right" sx={{ width: 66 }}>
                  <Tooltip title={SNR_HELP}><Box component="span">Star SNR</Box></Tooltip>
                </TableCell>
                <SortHeader
                  label="Sky"
                  sort={sort}
                  active={sort === "background_desc" || sort === "background_asc"}
                  onClick={() => onSort(nextSort(sort, "background_desc", "background_asc"))}
                  align="right"
                  help={SKY_HELP}
                  width={76}
                />
              </>
            )}
            <SortHeader
              label="File"
              sort={sort}
              active={sort === "path"}
              onClick={() => onSort("path")}
            />
            {showRig && <TableCell sx={{ width: 120 }}>Rig</TableCell>}
            {showTarget && <TableCell sx={{ width: 140 }}>Target</TableCell>}
            <TableCell sx={{ width: 76 }} />
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row, index) => {
            const showNight = timeSorted &&
              (index === 0 || row.observing_night !== rows[index - 1].observing_night);
            return (
              <FrameRows
                key={row.id}
                row={row}
                projectId={projectId}
                timezone={timezone}
                timeSorted={timeSorted}
                showNight={showNight}
                columnCount={columnCount}
                calibration={calibration}
                showRig={showRig}
                showTarget={showTarget}
                selected={selected.has(subFrameSelectionKey(row.id))}
                onToggleSelect={onToggleSelect}
                onOpen={onOpen}
                onCorrect={onCorrect}
              />
            );
          })}
        </TableBody>
      </Table>
    </CatalogInfiniteScroller>
  );
}

interface RowProps {
  row: CatalogFrame;
  projectId: number;
  timezone: string;
  timeSorted: boolean;
  showNight: boolean;
  columnCount: number;
  calibration: boolean;
  showRig: boolean;
  showTarget: boolean;
  selected: boolean;
  onToggleSelect: (key: CatalogSelectionKey, shift: boolean) => void;
  onOpen: (row: CatalogFrame) => void;
  onCorrect: (row: CatalogFrame) => void;
}

const FrameRows = memo(function FrameRows({
  row,
  projectId,
  timezone,
  timeSorted,
  showNight,
  columnCount,
  calibration,
  showRig,
  showTarget,
  selected,
  onToggleSelect,
  onOpen,
  onCorrect,
}: RowProps) {
  const measuredColumns = calibration ? 2 : 4;
  const status = row.quality_analyzed_at ? row.quality_status : null;
  return (
    <>
      {showNight && (
        <TableRow>
          <TableCell
            colSpan={columnCount}
            sx={(theme) => ({
              py: "7px",
              bgcolor: theme.palette.mode === "dark"
                ? "color-mix(in srgb, #31343a 60%, transparent)"
                : "color-mix(in srgb, #ebe8e3 60%, transparent)",
              fontSize: "12.5px !important",
              fontWeight: "600 !important",
            })}
          >
            {row.observing_night ? formatNight(row.observing_night) : "Capture time unknown"}
          </TableCell>
        </TableRow>
      )}
      <TableRow hover selected={selected}>
        <TableCell padding="checkbox">
          <Checkbox
            size="small"
            checked={selected}
            onChange={(event) =>
              onToggleSelect(
                subFrameSelectionKey(row.id),
                (event.nativeEvent as MouseEvent).shiftKey,
              )
            }
            inputProps={{ "aria-label": `select ${row.path ?? row.id}` }}
            sx={{ width: 32, height: 32, p: "4px" }}
          />
        </TableCell>
        <TableCell sx={{ width: 48 }}>
          <Box
            component="img"
            src={catalogThumbnailUrl(projectId, row.id)}
            alt=""
            loading="lazy"
            sx={{ width: 36, height: 24, display: "block", objectFit: "cover", borderRadius: "3px", bgcolor: "action.hover" }}
            onError={(event) => { event.currentTarget.style.visibility = "hidden"; }}
          />
        </TableCell>
        <TableCell title={formatDate(row.date_obs_utc, timezone)} sx={{ whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
          {captureDate(row.date_obs_utc, timezone, !timeSorted)}
        </TableCell>
        <TableCell title={row.filter_name ?? "Not recorded"}>
          <Box sx={{ display: "flex", alignItems: "center", gap: "6px", minWidth: 0 }}>
              <FilterSwatch
                filter={row.filter_name ? resolveFilterLabel(row.filter_name) : notRecordedFilter()}
              />
              <Typography
                component="span"
                sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "inherit" }}
              >
                {row.filter_name ?? "Not recorded"}
              </Typography>
            </Box>
        </TableCell>
        <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{formatSubExposure(row.exposure_seconds)}</TableCell>
        <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{row.gain ?? ""}</TableCell>
        <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{temperature(row.set_temp_c)}</TableCell>
        <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{row.binning?.replace("x", "×") ?? ""}</TableCell>
        {status === "unreadable" || (!calibration && status === "no_stars") ? (
          <TableCell colSpan={measuredColumns} align="center">
            <Tooltip title={status === "unreadable" ? UNREADABLE_HELP : NO_STARS_HELP}>
              <Typography component="span" sx={{ color: "text.disabled", fontSize: "12.5px" }}>
                {status === "unreadable" ? "unreadable" : "no stars"}
              </Typography>
            </Tooltip>
          </TableCell>
        ) : !row.quality_analyzed_at ? (
          Array.from({ length: measuredColumns }, (_, index) => <TableCell key={index} />)
        ) : calibration ? (
          <>
            <AduCell label="Median" value={row.median_adu} fullScale={row.full_scale_adu} />
            <AduCell label="Sky background" value={row.background_adu} fullScale={row.full_scale_adu} />
          </>
        ) : (
          <>
            <HfrCell row={row} />
            <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{row.star_count?.toLocaleString() ?? ""}</TableCell>
            <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{row.snr_estimate?.toFixed(0) ?? ""}</TableCell>
            <AduCell label="Sky background" value={row.background_adu} fullScale={row.full_scale_adu} />
          </>
        )}
        <TableCell sx={{ minWidth: 140, overflow: "hidden" }}>
          <Tooltip title={row.path ?? ""}>
            <Typography sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "text.secondary", fontSize: "13px" }}>
              {fileName(row.path)}
            </Typography>
          </Tooltip>
        </TableCell>
        {showRig && <TableCell>{row.rig_name ?? ""}</TableCell>}
        {showTarget && <TableCell>{row.target_name ?? ""}</TableCell>}
        <TableCell align="right" sx={{ py: "0 !important", whiteSpace: "nowrap" }}>
          {row.path && (
            <Tooltip title="Open in the Image Analyzer">
              <IconButton size="small" aria-label="open in image analyzer" onClick={() => onOpen(row)} sx={{ minWidth: 32, minHeight: 32 }}>
                <OpenInFullIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          <Tooltip title="Classification (frame type / target)">
            <IconButton size="small" aria-label="correct classification" onClick={() => onCorrect(row)} sx={{ minWidth: 32, minHeight: 32 }}>
              <EditNoteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </TableCell>
      </TableRow>
    </>
  );
});

function HfrCell({ row }: { row: CatalogFrame }) {
  if (row.hfr == null) return <TableCell />;
  const text = row.hfr_arcsec != null ? `${row.hfr_arcsec.toFixed(2)}″` : `${row.hfr.toFixed(2)} px`;
  const tooltip = row.hfr_arcsec != null
    ? `Half-Flux Radius: ${row.hfr_arcsec.toFixed(2)}″ (${row.hfr.toFixed(2)} px at ${row.pixel_scale_arcsec?.toFixed(3)}″/px, from the rig tagged on this frame's source folder). Lower is sharper; arcseconds are comparable between rigs.`
    : `Half-Flux Radius: ${row.hfr.toFixed(2)} px. Lower is sharper. Tag this frame's source folder with a rig to convert it to arcseconds, which is comparable between rigs.`;
  return <TableCell align="right" title={tooltip} sx={{ fontVariantNumeric: "tabular-nums" }}>{text}</TableCell>;
}

function AduCell({ label, value, fullScale }: { label: "Median" | "Sky background"; value: number | null; fullScale: number | null }) {
  return (
    <TableCell
      align="right"
      title={value == null ? undefined : aduTooltip(label, value, fullScale)}
      sx={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}
    >
      {aduText(value)}
    </TableCell>
  );
}
