import Autocomplete from "@mui/material/Autocomplete";
import CircularProgress from "@mui/material/CircularProgress";
import TextField from "@mui/material/TextField";
import { useQuery } from "@tanstack/react-query";
import { fetchSensors, type Sensor } from "@/api/equipment";

interface SensorPickerProps {
  value: number | null;
  onChange: (id: number | null) => void;
  label?: string;
  required?: boolean;
  error?: boolean;
  helperText?: string;
}

function formatSensorLabel(sensor: Sensor): string {
  return `${sensor.model_name} (${sensor.sensor_type}, ${sensor.pixel_size_um}µm, ${sensor.resolution_x}×${sensor.resolution_y})`;
}

export default function SensorPicker({
  value,
  onChange,
  label = "Sensor",
  required,
  error,
  helperText,
}: SensorPickerProps) {
  const { data: sensors = [], isLoading } = useQuery({
    queryKey: ["sensors"],
    queryFn: () => fetchSensors(),
  });

  const selectedOption = sensors.find((s) => s.id === value) ?? null;

  return (
    <Autocomplete<Sensor>
      options={sensors}
      loading={isLoading}
      value={selectedOption}
      onChange={(_event, option) => onChange(option ? option.id : null)}
      getOptionLabel={formatSensorLabel}
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
