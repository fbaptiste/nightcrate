import type { Ref } from "react";
import IconButton from "@mui/material/IconButton";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";

interface Props {
  label: string;
  onClick: () => void;
  size: "regular" | "compact";
  buttonRef?: Ref<HTMLButtonElement>;
}

export default function ExpandButton({ label, onClick, size, buttonRef }: Props) {
  const compact = size === "compact";
  return (
    <IconButton
      ref={buttonRef}
      aria-label={label}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      sx={{
        position: "absolute",
        zIndex: 3,
        top: compact ? 6 : 8,
        right: compact ? 6 : 8,
        width: compact ? 28 : 32,
        height: compact ? 28 : 32,
        color: "common.white",
        bgcolor: "rgba(0, 0, 0, 0.55)",
        border: "1px solid rgba(255, 255, 255, 0.28)",
        "&:hover": { bgcolor: "rgba(0, 0, 0, 0.8)" },
      }}
    >
      <OpenInFullIcon sx={{ fontSize: compact ? 15 : 18 }} />
    </IconButton>
  );
}
