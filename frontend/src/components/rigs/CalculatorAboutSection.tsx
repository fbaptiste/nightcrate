import { useState } from "react";
import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

interface CalculatorAboutSectionProps {
  children: React.ReactNode;
  /** Label override for the toggle row; defaults to "About this calculator". */
  label?: string;
}

/**
 * Collapsed-by-default disclosure showing attribution + methodology notes
 * beneath a calculator panel. Consumers pass in formatted JSX so each
 * calculator can tailor its own wording.
 */
export default function CalculatorAboutSection({
  children,
  label = "About this calculator",
}: CalculatorAboutSectionProps) {
  const [open, setOpen] = useState(false);
  return (
    <Box sx={{ mt: 2 }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 0.5,
          cursor: "pointer",
          userSelect: "none",
        }}
        onClick={() => setOpen((v) => !v)}
      >
        <IconButton size="small" sx={{ p: 0 }}>
          <ExpandMoreIcon
            sx={{
              transform: open ? "rotate(180deg)" : "none",
              transition: "transform 0.2s",
              fontSize: 18,
            }}
          />
        </IconButton>
        <Typography variant="caption" color="text.secondary">
          {label}
        </Typography>
      </Box>
      <Collapse in={open}>
        <Box
          sx={{
            pt: 1,
            maxWidth: 640,
            "& p": { mb: 1, lineHeight: 1.6 },
            "& p:last-child": { mb: 0 },
            "& strong": { fontWeight: 600 },
            "& code": {
              fontFamily: "monospace",
              fontSize: "0.85em",
              bgcolor: "action.hover",
              px: 0.5,
              borderRadius: 0.5,
            },
            "& ul": { pl: 2.5, my: 0.5 },
            "& li": { mb: 0.25 },
          }}
        >
          {children}
        </Box>
      </Collapse>
    </Box>
  );
}

export { Link as AboutLink };
