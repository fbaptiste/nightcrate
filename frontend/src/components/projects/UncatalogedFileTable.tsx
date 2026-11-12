import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import IconButton from "@mui/material/IconButton";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { UncatalogedFile } from "@/api/projectCatalog";
import { CatalogInfiniteScroller } from "./CatalogCardList";
import { formatDate } from "./CatalogCards";

interface Props {
  rows: UncatalogedFile[];
  timezone: string;
  loading: boolean;
  onOpen: (row: UncatalogedFile) => void;
}

const REASON_LABELS: Record<UncatalogedFile["reason"], string> = {
  damaged: "Damaged",
  unsupported: "Unsupported",
  unreadable: "Unreadable",
};

function fileName(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}

export default function UncatalogedFileTable({
  rows,
  timezone,
  loading,
  onOpen,
}: Props) {
  return (
    <CatalogInfiniteScroller
      itemCount={rows.length}
      hasMore={false}
      fetchingMore={false}
      onLoadMore={() => undefined}
      loading={loading}
      emptyMessage="No files are listed. A scan lists here any FITS or XISF file it couldn't catalog."
    >
      <Table
        stickyHeader
        size="small"
        sx={{
          minWidth: 640,
          border: 1,
          borderColor: "divider",
          tableLayout: "fixed",
          "& th": {
            px: "6px",
            py: "2px",
            color: "text.secondary",
            fontSize: "12px",
            fontWeight: 500,
          },
          "& td": { px: "6px", py: "4px", fontSize: "13px", verticalAlign: "top" },
        }}
      >
        <TableHead>
          <TableRow>
            <TableCell sx={{ width: "34%" }}>File</TableCell>
            <TableCell sx={{ width: 110 }}>Reason</TableCell>
            <TableCell>Details</TableCell>
            <TableCell sx={{ width: 130 }}>Found</TableCell>
            <TableCell sx={{ width: 52 }} />
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.id} hover>
              <TableCell sx={{ overflowWrap: "anywhere" }}>
                <Typography sx={{ fontSize: "inherit", lineHeight: "inherit", fontWeight: 500 }}>
                  {fileName(row.path)}
                </Typography>
                <Typography
                  sx={{
                    mt: "2px",
                    color: "text.secondary",
                    fontSize: "12px",
                    lineHeight: 1.35,
                    overflowWrap: "anywhere",
                  }}
                >
                  {row.path}
                </Typography>
              </TableCell>
              <TableCell>{REASON_LABELS[row.reason]}</TableCell>
              <TableCell sx={{ overflowWrap: "anywhere" }}>
                <Typography sx={{ fontSize: "inherit", lineHeight: "inherit" }}>
                  {row.message}
                </Typography>
                {row.cataloged_earlier && (
                  <Typography
                    sx={{ mt: "2px", color: "text.secondary", fontSize: "12px", lineHeight: 1.35 }}
                  >
                    An earlier scan cataloged this file.
                  </Typography>
                )}
              </TableCell>
              <TableCell>
                {formatDate(row.detected_at, timezone)}
              </TableCell>
              <TableCell align="right" sx={{ py: "0 !important" }}>
                <Tooltip title="Open in the Image Analyzer">
                  <IconButton
                    size="small"
                    aria-label="open in image analyzer"
                    onClick={() => onOpen(row)}
                    sx={{ minWidth: 32, minHeight: 32 }}
                  >
                    <OpenInFullIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </CatalogInfiniteScroller>
  );
}
