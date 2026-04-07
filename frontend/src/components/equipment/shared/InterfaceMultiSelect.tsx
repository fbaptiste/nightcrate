import { useRef, useState } from "react";
import AddIcon from "@mui/icons-material/Add";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import MenuItem from "@mui/material/MenuItem";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { fetchConnectionInterfaces, type ConnectionInterface } from "@/api/equipment";

interface InterfaceMultiSelectProps {
  value: number[];
  onChange: (ids: number[]) => void;
  label?: string;
}

export default function InterfaceMultiSelect({
  value,
  onChange,
  label = "Connection Interfaces",
}: InterfaceMultiSelectProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLButtonElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const { data: allInterfaces = [], isLoading } = useQuery({
    queryKey: ["connection-interfaces"],
    queryFn: () => fetchConnectionInterfaces(),
  });

  const selectedInterfaces = allInterfaces.filter((iface) => value.includes(iface.id));
  const availableInterfaces = allInterfaces.filter((iface) => !value.includes(iface.id));

  const handleRemove = (id: number) => {
    onChange(value.filter((v) => v !== id));
  };

  const handleAdd = (iface: ConnectionInterface) => {
    onChange([...value, iface.id]);
    setAnchorEl(null);
  };

  const open = Boolean(anchorEl);

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
        {label}
      </Typography>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, alignItems: "center" }}>
        {selectedInterfaces.map((iface) => (
          <Chip
            key={iface.id}
            label={iface.name}
            size="small"
            onDelete={() => handleRemove(iface.id)}
          />
        ))}
        {isLoading ? (
          <CircularProgress size={20} />
        ) : (
          <Button
            ref={buttonRef}
            size="small"
            startIcon={<AddIcon />}
            onClick={(e) => setAnchorEl(e.currentTarget)}
            disabled={availableInterfaces.length === 0}
            sx={{ minWidth: 0 }}
          >
            Add
          </Button>
        )}
      </Box>
      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
      >
        <Box sx={{ py: 0.5, minWidth: 160, maxHeight: 300, overflowY: "auto" }}>
          {availableInterfaces.length === 0 ? (
            <MenuItem disabled>
              <Typography variant="body2">All interfaces selected</Typography>
            </MenuItem>
          ) : (
            availableInterfaces.map((iface) => (
              <MenuItem key={iface.id} onClick={() => handleAdd(iface)} dense>
                {iface.name}
              </MenuItem>
            ))
          )}
        </Box>
      </Popover>
    </Box>
  );
}
