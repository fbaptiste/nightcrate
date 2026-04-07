import Autocomplete from "@mui/material/Autocomplete";
import CircularProgress from "@mui/material/CircularProgress";
import TextField from "@mui/material/TextField";
import { useQuery } from "@tanstack/react-query";

interface LookupItem {
  id: number;
  name: string;
}

interface LookupPickerProps<T extends LookupItem> {
  fetchFn: (includeRetired?: boolean) => Promise<T[]>;
  queryKey: string;
  value: number | null;
  onChange: (id: number | null) => void;
  label: string;
  getOptionLabel?: (item: T) => string;
  required?: boolean;
  error?: boolean;
  helperText?: string;
}

export default function LookupPicker<T extends LookupItem>({
  fetchFn,
  queryKey,
  value,
  onChange,
  label,
  getOptionLabel,
  required,
  error,
  helperText,
}: LookupPickerProps<T>) {
  const { data: items = [], isLoading } = useQuery({
    queryKey: [queryKey],
    queryFn: () => fetchFn(),
  });

  const resolveLabel = getOptionLabel ?? ((item: T) => item.name);
  const selectedOption = items.find((item) => item.id === value) ?? null;

  return (
    <Autocomplete<T>
      options={items}
      loading={isLoading}
      value={selectedOption}
      onChange={(_event, option) => onChange(option ? option.id : null)}
      getOptionLabel={resolveLabel}
      isOptionEqualToValue={(option, val) => option.id === val.id}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          required={required}
          error={error}
          helperText={helperText}
          slotProps={{
            input: {
              ...params.InputProps,
              endAdornment: (
                <>
                  {isLoading ? <CircularProgress color="inherit" size={20} /> : null}
                  {params.InputProps.endAdornment}
                </>
              ),
            },
          }}
        />
      )}
    />
  );
}
