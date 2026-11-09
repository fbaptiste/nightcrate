import { memo, useMemo } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { catalogThumbnailUrl, type CatalogFrame } from "@/api/projectCatalog";
import { formatNight } from "@/lib/localDate";
import { CatalogInfiniteScroller } from "./CatalogCardList";

interface Props {
  rows: CatalogFrame[];
  projectId: number;
  timezone: string;
  showNightHeadings: boolean;
  onOpen: (row: CatalogFrame) => void;
  hasMore: boolean;
  fetchingMore: boolean;
  onLoadMore: () => void;
  loading: boolean;
}

function captureTime(value: string | null, timezone: string, withDate: boolean): string {
  if (!value) return "Time unknown";
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

export default function CatalogThumbnailSheet({
  rows,
  projectId,
  timezone,
  showNightHeadings,
  onOpen,
  hasMore,
  fetchingMore,
  onLoadMore,
  loading,
}: Props) {
  const groups = useMemo(() => {
    if (!showNightHeadings) return [{ night: undefined, rows }];
    const result: { night: string | null | undefined; rows: CatalogFrame[] }[] = [];
    for (const row of rows) {
      const last = result[result.length - 1];
      if (!last || last.night !== row.observing_night) {
        result.push({ night: row.observing_night, rows: [row] });
      } else {
        last.rows.push(row);
      }
    }
    return result;
  }, [rows, showNightHeadings]);

  return (
    <CatalogInfiniteScroller
      itemCount={rows.length}
      hasMore={hasMore}
      fetchingMore={fetchingMore}
      onLoadMore={onLoadMore}
      loading={loading}
      emptyMessage="Nothing in this category yet."
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {groups.map((group, index) => (
          <Box key={`${group.night ?? "unknown"}:${index}`}>
            {showNightHeadings && (
              <Typography
                sx={(theme) => ({
                  px: "10px",
                  py: "7px",
                  mb: "6px",
                  bgcolor: theme.palette.mode === "dark"
                    ? "color-mix(in srgb, #31343a 60%, transparent)"
                    : "color-mix(in srgb, #ebe8e3 60%, transparent)",
                  fontSize: "12.5px",
                  fontWeight: 600,
                })}
              >
                {group.night ? formatNight(group.night) : "Capture time unknown"}
              </Typography>
            )}
            <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: "10px" }}>
              {group.rows.map((row) => (
                <ThumbnailCard
                  key={row.id}
                  row={row}
                  projectId={projectId}
                  timezone={timezone}
                  showNightHeading={showNightHeadings}
                  onOpen={onOpen}
                />
              ))}
            </Box>
          </Box>
        ))}
      </Box>
    </CatalogInfiniteScroller>
  );
}

const ThumbnailCard = memo(function ThumbnailCard({
  row,
  projectId,
  timezone,
  showNightHeading,
  onOpen,
}: {
  row: CatalogFrame;
  projectId: number;
  timezone: string;
  showNightHeading: boolean;
  onOpen: (row: CatalogFrame) => void;
}) {
  const hfr = row.hfr == null
    ? null
    : row.hfr_arcsec != null
      ? `${row.hfr_arcsec.toFixed(1)}″`
      : `${row.hfr.toFixed(1)} px`;
  const detail = [
    row.filter_name,
    row.star_count == null ? "not analyzed" : `${row.star_count.toLocaleString()} stars`,
  ]
    .filter(Boolean)
    .join(", ");
  return (
    <Box
      role="button"
      tabIndex={0}
      onClick={() => onOpen(row)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(row);
        }
      }}
      sx={(theme) => ({
        bgcolor: "background.paper",
        border: 1,
        borderColor: theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4",
        borderRadius: "6px",
        overflow: "hidden",
        cursor: "pointer",
        "&:focus-visible": { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: "2px" },
      })}
    >
      <Box sx={{ height: 96, position: "relative", bgcolor: "common.black" }}>
        <Box
          component="img"
          src={catalogThumbnailUrl(projectId, row.id)}
          alt=""
          loading="lazy"
          sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
        />
        {hfr && (
          <Typography
            sx={{
              position: "absolute",
              top: 6,
              right: 6,
              px: "7px",
              py: "1px",
              borderRadius: "9px",
              bgcolor: "rgba(0, 0, 0, 0.55)",
              color: "common.white",
              fontSize: "11px",
            }}
          >
            {hfr}
          </Typography>
        )}
      </Box>
      <Box sx={{ px: "8px", py: "6px" }}>
        <Typography sx={{ fontSize: "12.5px", fontWeight: 600 }}>
          {captureTime(row.date_obs_utc, timezone, !showNightHeading)}
        </Typography>
        <Typography sx={{ color: "text.secondary", fontSize: "12px" }}>
          {detail}
        </Typography>
      </Box>
    </Box>
  );
});
