import Box from "@mui/material/Box";
import { fovGeometry } from "@/lib/messierFov";

interface Props {
  picture: { widthDeg: number; heightDeg: number } | null;
  rig: { majorDeg: number; minorDeg: number } | null;
  showUnknown?: boolean;
  small?: boolean;
}

export default function RigFieldBox({ picture, rig, showUnknown = false, small = false }: Props) {
  const geometry = picture && rig ? fovGeometry(picture, rig) : null;
  if (!rig) return null;
  if (!geometry) {
    return showUnknown ? (
      <Box sx={{ position: "absolute", left: small ? 6 : 8, bottom: small ? 6 : 8, height: 22, px: "9px", borderRadius: 11, display: "inline-flex", alignItems: "center", bgcolor: "rgba(0, 0, 0, 0.66)", border: "1px solid rgba(255, 255, 255, 0.32)", color: "#ffffff", fontSize: 11, fontWeight: 600, pointerEvents: "none" }}>
        Scale unknown
      </Box>
    ) : null;
  }
  return (
    <Box
      aria-hidden
      sx={{
        position: "absolute",
        left: "50%",
        top: "50%",
        transform: "translate(-50%, -50%)",
        width: `${geometry.boxWidthPct}%`,
        height: `${geometry.boxHeightPct}%`,
        border: "2px solid #ed6c02",
        boxShadow: "0 0 0 1px rgba(0, 0, 0, 0.5)",
        pointerEvents: "none",
      }}
    />
  );
}
