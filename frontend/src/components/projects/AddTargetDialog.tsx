import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import { fetchDsos } from "@/api/dsos";
import type { DsoListItem } from "@/api/dsos";

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (dsoId: number) => Promise<unknown>;
  excludeDsoIds: Set<number>;
}

export default function AddTargetDialog({ open, onClose, onSelect, excludeDsoIds }: Props) {
  const [input, setInput] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebounced(input), 250);
    return () => clearTimeout(t);
  }, [input]);

  const { data, isFetching } = useQuery({
    queryKey: ["dso-search", debounced],
    queryFn: () => fetchDsos({ q: debounced || null, limit: 25 }),
    enabled: open,
  });

  const options = (data?.items ?? []).filter((o) => !excludeDsoIds.has(o.id));

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add target</DialogTitle>
      <DialogContent>
        <Autocomplete
          sx={{ mt: 1 }}
          options={options}
          loading={isFetching}
          // Server already returns matches; don't double-filter client-side.
          filterOptions={(x) => x}
          getOptionLabel={(o: DsoListItem) =>
            o.common_name ? `${o.primary_designation} — ${o.common_name}` : o.primary_designation
          }
          isOptionEqualToValue={(o, v) => o.id === v.id}
          onInputChange={(_e, value) => setInput(value)}
          onChange={async (_e, v) => {
            if (!v) return;
            await onSelect(v.id);
            onClose();
          }}
          renderOption={(props, option) => (
            <li {...props} key={option.id}>
              <Box>
                <Typography variant="body2">
                  {option.primary_designation}
                  {option.common_name ? ` — ${option.common_name}` : ""}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {option.obj_type}
                  {option.constellation ? ` · ${option.constellation}` : ""}
                </Typography>
              </Box>
            </li>
          )}
          renderInput={(params) => (
            <TextField
              {...params}
              autoFocus
              label="Search DSOs"
              placeholder="M31, NGC 5128, Crab..."
            />
          )}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
      </DialogActions>
    </Dialog>
  );
}
