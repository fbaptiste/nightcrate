import Box from "@mui/material/Box";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import type { HeaderCard } from "@/api/fits";

const columns: GridColDef[] = [
  {
    field: "key",
    headerName: "Keyword",
    width: 130,
    renderCell: (params) => (
      <Box component="span" sx={{ fontFamily: "monospace", fontSize: "0.8rem", fontWeight: 600 }}>
        {params.value}
      </Box>
    ),
  },
  {
    field: "value",
    headerName: "Value",
    width: 200,
    renderCell: (params) => (
      <Box component="span" sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
        {params.value}
      </Box>
    ),
  },
  {
    field: "comment",
    headerName: "Comment",
    flex: 1,
    renderCell: (params) => (
      <Box component="span" sx={{ fontSize: "0.8rem", color: "text.secondary" }}>
        {params.value}
      </Box>
    ),
  },
];

interface Props {
  cards: HeaderCard[];
}

export function FitsHeaderTable({ cards }: Props) {
  const rows = cards.map((card, i) => ({ id: i, ...card }));

  return (
    <DataGrid
      rows={rows}
      columns={columns}
      density="compact"
      disableRowSelectionOnClick
      hideFooterSelectedRowCount
      pageSizeOptions={[50, 100, 200]}
      initialState={{ pagination: { paginationModel: { pageSize: 100 } } }}
      sx={{ border: 0, height: "100%" }}
    />
  );
}
