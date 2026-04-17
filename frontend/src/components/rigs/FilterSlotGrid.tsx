import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import StarIcon from "@mui/icons-material/Star";
import type { FilterOption } from "@/api/rigs";
import { withMineGroup } from "@/components/rigs/mineGroup";

interface FilterSlotGridProps {
  numPositions: number;
  filters: FilterOption[];
  slots: { slot_number: number; filter_id: number }[];
  onChange: (slots: { slot_number: number; filter_id: number }[]) => void;
}

export default function FilterSlotGrid({
  numPositions,
  filters,
  slots,
  onChange,
}: FilterSlotGridProps) {
  const handleSlotChange = (slotNumber: number, filter: FilterOption | null) => {
    const updated = slots.filter((s) => s.slot_number !== slotNumber);
    if (filter) {
      updated.push({ slot_number: slotNumber, filter_id: filter.id });
    }
    onChange(updated);
  };

  const groupedOptions = withMineGroup(filters);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {Array.from({ length: numPositions }, (_, i) => {
        const slotNumber = i + 1;
        const assigned = slots.find((s) => s.slot_number === slotNumber);
        const selectedFilter = assigned
          ? filters.find((f) => f.id === assigned.filter_id) ?? null
          : null;

        return (
          <Box
            key={slotNumber}
            sx={{ display: "flex", alignItems: "center", gap: 1 }}
          >
            <Typography
              variant="body2"
              sx={{ width: 60, flexShrink: 0, textAlign: "right" }}
            >
              Slot {slotNumber}
            </Typography>
            <Autocomplete<FilterOption & { __mine_group?: string }>
              size="small"
              options={groupedOptions}
              groupBy={(o) => o.__mine_group ?? o.manufacturer_name}
              value={selectedFilter}
              onChange={(_e, value) => handleSlotChange(slotNumber, value)}
              getOptionLabel={(o) =>
                `${o.manufacturer_name} \u2014 ${o.model_name}`
              }
              isOptionEqualToValue={(opt, val) => opt.id === val.id}
              renderOption={(props, option) => {
                const { key, ...rest } = props as typeof props & { key?: React.Key };
                return (
                  <li key={key} {...rest}>
                    {option.is_mine && (
                      <StarIcon
                        fontSize="small"
                        color="primary"
                        sx={{ mr: 0.75 }}
                      />
                    )}
                    {option.manufacturer_name} — {option.model_name}
                  </li>
                );
              }}
              renderInput={(params) => (
                <TextField {...params} placeholder="Select filter" />
              )}
              sx={{ flex: 1 }}
            />
          </Box>
        );
      })}
    </Box>
  );
}
