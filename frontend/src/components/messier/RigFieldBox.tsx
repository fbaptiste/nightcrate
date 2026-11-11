import Box from "@mui/material/Box";
import { fovGeometry, rigViewGeometry } from "@/lib/messierFov";

interface Props {
  picture: { widthDeg: number; heightDeg: number };
  rig: { majorDeg: number; minorDeg: number };
  fieldDeg?: number;
}

export default function RigFieldBox({ picture, rig, fieldDeg }: Props) {
  const geometry = fieldDeg != null
    ? rigViewGeometry(fieldDeg, rig)
    : fovGeometry(picture, rig);
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
