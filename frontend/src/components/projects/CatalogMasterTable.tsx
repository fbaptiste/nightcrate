import { memo } from "react";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import Checkbox from "@mui/material/Checkbox";
import IconButton from "@mui/material/IconButton";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { CatalogMaster } from "@/api/projectCatalog";
import { CatalogInfiniteScroller } from "./CatalogCardList";
import { formatDate, formatExposure, formatSize } from "./CatalogCards";
import {
  processedImageSelectionKey,
  type CatalogSelectionKey,
} from "./catalogSelection";

interface Props {
  rows: CatalogMaster[];
  timezone: string;
  selected: Set<CatalogSelectionKey>;
  onToggleSelect: (key: CatalogSelectionKey, shift: boolean) => void;
  onOpen: (row: CatalogMaster) => void;
  hasMore: boolean;
  fetchingMore: boolean;
  onLoadMore: () => void;
  loading: boolean;
}

function fileName(path: string | null): string {
  return path?.split(/[\\/]/).pop() ?? "";
}

export default function CatalogMasterTable({
  rows,
  timezone,
  selected,
  onToggleSelect,
  onOpen,
  hasMore,
  fetchingMore,
  onLoadMore,
  loading,
}: Props) {
  return (
    <CatalogInfiniteScroller itemCount={rows.length} hasMore={hasMore} fetchingMore={fetchingMore} onLoadMore={onLoadMore} loading={loading} emptyMessage="Nothing in this category yet.">
      <Table stickyHeader size="small" sx={{ minWidth: 980, border: 1, borderColor: "divider", "& th": { color: "text.secondary", fontSize: "12px", fontWeight: 500 }, "& td": { fontSize: "13px" } }}>
        <TableHead>
          <TableRow>
            <TableCell padding="checkbox" />
            <TableCell>Type</TableCell>
            <TableCell>Filter</TableCell>
            <TableCell align="right">Frames combined</TableCell>
            <TableCell align="right">Total exposure</TableCell>
            <TableCell>Dimensions</TableCell>
            <TableCell align="right">Size</TableCell>
            <TableCell>Date</TableCell>
            <TableCell>File</TableCell>
            <TableCell />
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <MasterRow key={row.id} row={row} timezone={timezone} selected={selected.has(processedImageSelectionKey(row.id))} onToggleSelect={onToggleSelect} onOpen={onOpen} />
          ))}
        </TableBody>
      </Table>
    </CatalogInfiniteScroller>
  );
}

const MasterRow = memo(function MasterRow({ row, timezone, selected, onToggleSelect, onOpen }: {
  row: CatalogMaster;
  timezone: string;
  selected: boolean;
  onToggleSelect: (key: CatalogSelectionKey, shift: boolean) => void;
  onOpen: (row: CatalogMaster) => void;
}) {
  return (
    <TableRow hover selected={selected}>
      <TableCell padding="checkbox"><Checkbox size="small" checked={selected} onChange={(event) => onToggleSelect(processedImageSelectionKey(row.id), (event.nativeEvent as MouseEvent).shiftKey)} inputProps={{ "aria-label": `select ${row.path ?? row.id}` }} /></TableCell>
      <TableCell>{row.type_label}</TableCell>
      <TableCell>{row.filter_name ?? ""}</TableCell>
      <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{row.ncombine ?? ""}</TableCell>
      <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{formatExposure(row.total_exposure_seconds)}</TableCell>
      <TableCell>{row.dimensions ?? ""}</TableCell>
      <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>{formatSize(row.file_size_bytes)}</TableCell>
      <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(row.date_obs_utc, timezone)}</TableCell>
      <TableCell sx={{ maxWidth: 280 }}><Tooltip title={row.path ?? ""}><Typography sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "text.secondary", fontSize: "13px" }}>{fileName(row.path)}</Typography></Tooltip></TableCell>
      <TableCell align="right">
        {row.path && <Tooltip title="Open in the Image Analyzer"><IconButton size="small" aria-label="open in image analyzer" onClick={() => onOpen(row)} sx={{ minWidth: 32, minHeight: 32 }}><OpenInFullIcon fontSize="small" /></IconButton></Tooltip>}
      </TableCell>
    </TableRow>
  );
});
