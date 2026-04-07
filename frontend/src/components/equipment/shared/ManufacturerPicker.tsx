import Autocomplete from "@mui/material/Autocomplete";
import CircularProgress from "@mui/material/CircularProgress";
import TextField from "@mui/material/TextField";
import { useQuery } from "@tanstack/react-query";
import { fetchManufacturers, type Manufacturer } from "@/api/equipment";

interface ManufacturerPickerProps {
  value: number | null;
  onChange: (id: number | null) => void;
  label?: string;
  required?: boolean;
  error?: boolean;
  helperText?: string;
}

export default function ManufacturerPicker({
  value,
  onChange,
  label = "Manufacturer",
  required,
  error,
  helperText,
}: ManufacturerPickerProps) {
  const { data: manufacturers = [], isLoading } = useQuery({
    queryKey: ["manufacturers"],
    queryFn: () => fetchManufacturers(),
  });

  const selectedOption = manufacturers.find((m) => m.id === value) ?? null;

  return (
    <Autocomplete<Manufacturer>
      options={manufacturers}
      loading={isLoading}
      value={selectedOption}
      onChange={(_event, option) => onChange(option ? option.id : null)}
      getOptionLabel={(option) => option.name}
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
