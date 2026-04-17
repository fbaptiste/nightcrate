import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import StarIcon from "@mui/icons-material/Star";
import StarOutlineIcon from "@mui/icons-material/StarOutline";

interface MineCheckboxProps {
  value: boolean;
  onChange: (value: boolean) => void;
}

export default function MineCheckbox({ value, onChange }: MineCheckboxProps) {
  return (
    <FormControlLabel
      control={
        <Checkbox
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
          icon={<StarOutlineIcon />}
          checkedIcon={<StarIcon color="primary" />}
        />
      }
      label={<Box sx={{ fontSize: "0.875rem" }}>Mark as mine (I own this)</Box>}
      sx={{ mb: 1 }}
    />
  );
}
