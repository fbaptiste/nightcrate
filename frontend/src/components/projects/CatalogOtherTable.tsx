import { memo } from "react";
import EditNoteIcon from "@mui/icons-material/EditNote";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import IconButton from "@mui/material/IconButton";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { catalogThumbnailUrl, type CatalogOther } from "@/api/projectCatalog";
import { CatalogInfiniteScroller } from "./CatalogCardList";
import { formatDate, formatSize } from "./CatalogCards";
import {
  fileSelectionKey,
  subFrameSelectionKey,
  type CatalogSelectionKey,
} from "./catalogSelection";

interface Props {
  rows: CatalogOther[];
  projectId: number;
  timezone: string;
  selected: Set<CatalogSelectionKey>;
  onToggleSelect: (key: CatalogSelectionKey, shift: boolean) => void;
  onOpen: (row: CatalogOther) => void;
  onCorrect: (row: CatalogOther) => void;
  hasMore: boolean;
  fetchingMore: boolean;
  onLoadMore: () => void;
  loading: boolean;
}

function fileName(path: string | null): string {
  return path?.split(/[\\/]/).pop() ?? "";
}

function selectionKey(row: CatalogOther): CatalogSelectionKey {
  return row.kind === "sub_frame"
    ? subFrameSelectionKey(row.id)
    : fileSelectionKey(row.id);
}

export default function CatalogOtherTable({ rows, projectId, timezone, selected, onToggleSelect, onOpen, onCorrect, hasMore, fetchingMore, onLoadMore, loading }: Props) {
  return (
    <CatalogInfiniteScroller itemCount={rows.length} hasMore={hasMore} fetchingMore={fetchingMore} onLoadMore={onLoadMore} loading={loading} emptyMessage="Nothing in this category yet.">
      <Table stickyHeader size="small" sx={{ minWidth: 808, border: 1, borderColor: "divider", "& th": { color: "text.secondary", fontSize: "12px", fontWeight: 500 }, "& td": { fontSize: "13px" } }}>
        <TableHead><TableRow><TableCell padding="checkbox" /><TableCell sx={{ width: 48 }} /><TableCell>Type</TableCell><TableCell>File</TableCell><TableCell align="right">Size</TableCell><TableCell>Date</TableCell><TableCell /></TableRow></TableHead>
        <TableBody>{rows.map((row) => <OtherRow key={`${row.kind}-${row.id}`} row={row} projectId={projectId} timezone={timezone} selected={selected.has(selectionKey(row))} onToggleSelect={onToggleSelect} onOpen={onOpen} onCorrect={onCorrect} />)}</TableBody>
      </Table>
    </CatalogInfiniteScroller>
  );
}

const OtherRow = memo(function OtherRow({ row, projectId, timezone, selected, onToggleSelect, onOpen, onCorrect }: {
  row: CatalogOther;
  projectId: number;
  timezone: string;
  selected: boolean;
  onToggleSelect: (key: CatalogSelectionKey, shift: boolean) => void;
  onOpen: (row: CatalogOther) => void;
  onCorrect: (row: CatalogOther) => void;
}) {
  const correctable = row.kind === "sub_frame";
  return (
    <TableRow hover selected={selected}>
      <TableCell padding="checkbox"><Checkbox size="small" checked={selected} onChange={(event) => onToggleSelect(selectionKey(row), (event.nativeEvent as MouseEvent).shiftKey)} inputProps={{ "aria-label": `select ${row.path ?? row.id}` }} /></TableCell>
      <TableCell sx={{ width: 48 }}>
        {correctable && (
          <Box
            component="img"
            src={catalogThumbnailUrl(projectId, row.id)}
            alt=""
            loading="lazy"
            sx={{ width: 36, height: 24, display: "block", objectFit: "cover", borderRadius: "3px", bgcolor: "action.hover" }}
            onError={(event) => { event.currentTarget.style.visibility = "hidden"; }}
          />
        )}
      </TableCell>
      <TableCell>{row.type_label}</TableCell>
      <TableCell sx={{ maxWidth: 420 }}><Tooltip title={row.path ?? ""}><Typography sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "text.secondary", fontSize: "13px" }}>{fileName(row.path)}</Typography></Tooltip></TableCell>
      <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>{formatSize(row.size_bytes)}</TableCell>
      <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(row.date, timezone)}</TableCell>
      <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
        {correctable && row.path && <Tooltip title="Open in the Image Analyzer"><IconButton size="small" aria-label="open in image analyzer" onClick={() => onOpen(row)} sx={{ minWidth: 32, minHeight: 32 }}><OpenInFullIcon fontSize="small" /></IconButton></Tooltip>}
        {correctable && <Tooltip title="Set this frame's type"><IconButton size="small" aria-label="set frame type" onClick={() => onCorrect(row)} sx={{ minWidth: 32, minHeight: 32 }}><EditNoteIcon fontSize="small" /></IconButton></Tooltip>}
      </TableCell>
    </TableRow>
  );
});
