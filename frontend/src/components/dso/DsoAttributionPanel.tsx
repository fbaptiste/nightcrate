import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import { fetchCatalogSources } from "@/api/dsos";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function DsoAttributionPanel({ open, onClose }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["catalog-sources"],
    queryFn: fetchCatalogSources,
    enabled: open,
  });

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ display: "flex", alignItems: "center" }}>
        <Box sx={{ flex: 1 }}>Catalog attribution</Box>
        <IconButton onClick={onClose} size="small">
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" sx={{ mb: 2 }}>
          Deep-sky object data in NightCrate is sourced from the catalogs below.
          NightCrate application code is MIT-licensed; each catalog's data file
          carries its own license, which must be preserved on redistribution.
        </Typography>

        {isLoading && <CircularProgress size={20} />}

        <Stack spacing={2}>
          {data?.map((source) => (
            <Box
              key={source.id}
              sx={{
                p: 2,
                border: 1,
                borderColor: "divider",
                borderRadius: 1,
              }}
            >
              <Typography variant="subtitle1" fontWeight={600}>
                {source.display_name}
              </Typography>
              <Stack spacing={0.5} sx={{ mt: 1 }}>
                {source.version && (
                  <Typography variant="caption" color="text.secondary">
                    Version: {source.version}
                  </Typography>
                )}
                <Typography variant="caption" color="text.secondary">
                  Rows loaded: {source.row_count.toLocaleString()}
                </Typography>
                {source.license && (
                  <Typography variant="caption" color="text.secondary">
                    License: {source.license}
                  </Typography>
                )}
                {source.source_url && (
                  <Typography variant="caption">
                    Upstream:{" "}
                    <Link href={source.source_url} target="_blank" rel="noopener noreferrer">
                      {source.source_url}
                    </Link>
                  </Typography>
                )}
                {source.attribution && (
                  <Typography variant="body2" sx={{ mt: 1, fontStyle: "italic" }}>
                    {source.attribution}
                  </Typography>
                )}
              </Stack>
            </Box>
          ))}
        </Stack>
      </DialogContent>
    </Dialog>
  );
}
