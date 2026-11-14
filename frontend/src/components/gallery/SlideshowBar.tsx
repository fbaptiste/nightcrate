import PauseIcon from "@mui/icons-material/Pause";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import type { SlideshowSeconds } from "@/api/settings";
import { SLIDESHOW_STEPS } from "./slideshow";

interface Props {
  playing: boolean;
  seconds: SlideshowSeconds;
  index: number;
  count: number;
  onToggle: () => void;
  onChangeInterval: (delta: 1 | -1) => void;
}

const buttonSx = {
  width: 44,
  height: 44,
  border: 0,
  color: "#e2e0dd",
  borderRadius: 999,
  "&:hover": { bgcolor: "rgba(255, 255, 255, 0.18)" },
  "&.Mui-disabled": { color: "#e2e0dd", opacity: 0.35 },
} as const;

export default function SlideshowBar({
  playing,
  seconds,
  index,
  count,
  onToggle,
  onChangeInterval,
}: Props) {
  const speedIndex = SLIDESHOW_STEPS.indexOf(seconds);
  const shortest = speedIndex === 0;
  const longest = speedIndex === SLIDESHOW_STEPS.length - 1;
  const shorter = SLIDESHOW_STEPS[Math.max(0, speedIndex - 1)];
  const longer = SLIDESHOW_STEPS[Math.min(SLIDESHOW_STEPS.length - 1, speedIndex + 1)];

  return (
    <Box
      role="toolbar"
      aria-label="Slideshow"
      sx={{
        display: "flex",
        alignItems: "center",
        gap: "4px",
        p: "4px",
        borderRadius: 999,
        bgcolor: "rgba(255, 255, 255, 0.06)",
        border: "1px solid rgba(255, 255, 255, 0.16)",
      }}
    >
      <IconButton
        aria-label={playing ? "Pause slideshow" : "Play slideshow"}
        disabled={count <= 1}
        onClick={onToggle}
        sx={{ ...buttonSx, bgcolor: "rgba(255, 255, 255, 0.12)" }}
      >
        {playing ? <PauseIcon sx={{ fontSize: 26 }} /> : <PlayArrowIcon sx={{ fontSize: 26 }} />}
      </IconButton>
      <Box aria-hidden sx={{ width: "1px", height: 24, bgcolor: "rgba(255, 255, 255, 0.16)", mx: "4px" }} />
      <IconButton
        aria-label={shortest ? "Shortest interval" : `Shorter interval: ${shorter} seconds per picture`}
        disabled={shortest}
        onClick={() => onChangeInterval(-1)}
        sx={{ ...buttonSx, fontSize: 22, lineHeight: 1 }}
      >
        {"−"}
      </IconButton>
      <Box sx={{ minWidth: 44, textAlign: "center", fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums", color: "#e2e0dd" }}>
        {seconds} s
      </Box>
      <IconButton
        aria-label={longest ? "Longest interval" : `Longer interval: ${longer} seconds per picture`}
        disabled={longest}
        onClick={() => onChangeInterval(1)}
        sx={{ ...buttonSx, fontSize: 22, lineHeight: 1 }}
      >
        +
      </IconButton>
      <Box aria-hidden sx={{ width: "1px", height: 24, bgcolor: "rgba(255, 255, 255, 0.16)", mx: "4px" }} />
      <Box
        aria-live={playing ? "off" : "polite"}
        sx={{ pl: "4px", pr: "14px", fontSize: 13, color: "#a3a09b", whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}
      >
        {index + 1} of {count}
      </Box>
    </Box>
  );
}
