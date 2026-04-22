/**
 * DataGrid pagination actions — First / Prev / page-number / Next / Last.
 *
 * Wire into any MUI X DataGrid via:
 *
 *     slotProps={{
 *       basePagination: {
 *         ActionsComponent: PaginationActions,
 *       } as any,
 *     }}
 *
 * (The ``as any`` sheds a MUI X typing gap where
 * ``basePagination.ActionsComponent`` is only loosely typed on the
 * slot-props side.)
 */
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import FirstPageIcon from "@mui/icons-material/FirstPage";
import KeyboardArrowLeftIcon from "@mui/icons-material/KeyboardArrowLeft";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import LastPageIcon from "@mui/icons-material/LastPage";

interface Props {
  count: number;
  page: number;
  rowsPerPage: number;
  onPageChange: (
    event: React.MouseEvent<HTMLButtonElement> | null,
    newPage: number,
  ) => void;
}

export default function PaginationActions({
  count,
  page,
  rowsPerPage,
  onPageChange,
}: Props) {
  const lastPage = Math.max(0, Math.ceil(count / rowsPerPage) - 1);
  // Fit-to-content width for the page-number input — grows with the
  // largest possible page number so 3-digit totals don't clip the
  // digits.
  const digitWidth = `calc(${String(lastPage + 1).length}ch + 30px)`;

  const gotoPage = (raw: string) => {
    const parsed = Number.parseInt(raw, 10);
    if (Number.isNaN(parsed)) return;
    const clamped = Math.max(0, Math.min(lastPage, parsed - 1));
    if (clamped !== page) onPageChange(null, clamped);
  };

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, ml: 1 }}>
      <IconButton
        size="small"
        onClick={(e) => onPageChange(e, 0)}
        disabled={page === 0}
        aria-label="first page"
      >
        <FirstPageIcon fontSize="small" />
      </IconButton>
      <IconButton
        size="small"
        onClick={(e) => onPageChange(e, page - 1)}
        disabled={page === 0}
        aria-label="previous page"
      >
        <KeyboardArrowLeftIcon fontSize="small" />
      </IconButton>
      <TextField
        size="small"
        type="number"
        value={page + 1}
        onChange={(e) => gotoPage(e.target.value)}
        inputProps={{
          min: 1,
          max: lastPage + 1,
          "aria-label": "go to page",
          style: { textAlign: "right", padding: "4px 6px" },
        }}
        sx={{ width: digitWidth }}
      />
      <Typography
        variant="caption"
        color="text.secondary"
        noWrap
        sx={{ mx: 0.5, flexShrink: 0 }}
      >
        of {lastPage + 1}
      </Typography>
      <IconButton
        size="small"
        onClick={(e) => onPageChange(e, page + 1)}
        disabled={page >= lastPage}
        aria-label="next page"
      >
        <KeyboardArrowRightIcon fontSize="small" />
      </IconButton>
      <IconButton
        size="small"
        onClick={(e) => onPageChange(e, lastPage)}
        disabled={page >= lastPage}
        aria-label="last page"
      >
        <LastPageIcon fontSize="small" />
      </IconButton>
    </Box>
  );
}
