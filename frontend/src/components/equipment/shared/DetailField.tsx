import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

interface DetailFieldProps {
  label: string;
  value: React.ReactNode;
}

/** Single label/value row for equipment detail panels. */
export default function DetailField({ label, value }: DetailFieldProps) {
  return (
    <Box sx={{ display: "flex", gap: 1.5, py: 0.3, alignItems: "baseline" }}>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ minWidth: 140, flexShrink: 0 }}
      >
        {label}
      </Typography>
      <Typography variant="body2">{value ?? "—"}</Typography>
    </Box>
  );
}
