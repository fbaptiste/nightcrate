import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Button from "@mui/material/Button";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";

import { fetchRigs, type Rig } from "@/api/rigs";

interface Props {
  onApply: (rig: Rig) => void;
  label?: string;
}

/**
 * "Populate from rig" picker used above calculator inputs. Lists all active
 * rigs; selecting one calls `onApply` so the host calculator can copy the
 * rig's equipment data into its own state. Host fields remain editable.
 */
export default function RigPickerMenu({
  onApply,
  label = "Populate from rig",
}: Props) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const { data: rigs } = useQuery<Rig[]>({
    queryKey: ["rigs", "calculator-picker"],
    queryFn: () => fetchRigs(true),
  });

  const open = Boolean(anchorEl);
  const hasRigs = (rigs?.length ?? 0) > 0;

  if (!hasRigs) {
    return (
      <Typography variant="caption" color="text.secondary">
        Build a rig on the Rigs page to auto-populate these fields.
      </Typography>
    );
  }

  return (
    <Stack direction="row" spacing={1} alignItems="center">
      <Button
        size="small"
        variant="outlined"
        endIcon={<KeyboardArrowDownIcon />}
        onClick={(e) => setAnchorEl(e.currentTarget)}
      >
        {label}
      </Button>
      <Menu
        anchorEl={anchorEl}
        open={open}
        onClose={() => setAnchorEl(null)}
        slotProps={{ paper: { sx: { minWidth: 240 } } }}
      >
        {rigs!.map((rig) => (
          <MenuItem
            key={rig.id}
            onClick={() => {
              onApply(rig);
              setAnchorEl(null);
            }}
          >
            <Stack>
              <Typography variant="body2">{rig.name}</Typography>
              <Typography variant="caption" color="text.secondary">
                {rig.telescope_name} &middot; {rig.camera_name}
              </Typography>
            </Stack>
          </MenuItem>
        ))}
      </Menu>
    </Stack>
  );
}
