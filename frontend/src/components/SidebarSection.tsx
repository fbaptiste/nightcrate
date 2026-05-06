import { useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

interface Props {
  label: string;
  children?: React.ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onToggle?: (open: boolean) => void;
  sx?: object;
}

export function SidebarSection({ label, children, defaultOpen = true, open: controlledOpen, onToggle, sx }: Props) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const isOpen = controlledOpen ?? internalOpen;
  const toggle = () => {
    const next = !isOpen;
    setInternalOpen(next);
    onToggle?.(next);
  };
  return (
    <>
      <Box
        onClick={toggle}
        sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.5, pt: 1.5, pb: 0.5, cursor: "pointer", userSelect: "none", ...sx }}
      >
        <Box sx={{ flex: 1, borderBottom: 1, borderColor: "secondary.main", opacity: 0.6 }} />
        <Typography variant="caption" color="secondary.main" sx={{ fontSize: "0.65rem", flexShrink: 0, letterSpacing: "0.05em", textTransform: "uppercase" }}>
          {isOpen ? `${label} ▴` : `${label} ▾`}
        </Typography>
        <Box sx={{ flex: 1, borderBottom: 1, borderColor: "secondary.main", opacity: 0.6 }} />
      </Box>
      {isOpen && children}
    </>
  );
}
