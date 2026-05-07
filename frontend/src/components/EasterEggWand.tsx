import { useRef, useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";

/** Shuffled queue so every line is seen before any repeats. */
function shuffleQueue(items: string[]): string[] {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

interface Props {
  lines: string[];
  tooltip?: string;
  size?: number;
}

export function EasterEggWand({ lines, tooltip = "Cast a spell", size = 14 }: Props) {
  const [casting, setCasting] = useState(false);
  const [line, setLine] = useState("");
  const [sparkles, setSparkles] = useState<{ id: number; x: number; y: number }[]>([]);
  const nextId = useRef(0);
  const queue = useRef<string[]>([]);

  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cast = () => {
    if (queue.current.length === 0) {
      queue.current = shuffleQueue(lines);
    }
    setLine(queue.current.pop()!);
    setCasting(true);

    const newSparkles = Array.from({ length: 8 }, () => ({
      id: nextId.current++,
      x: Math.random() * 40 - 20,
      y: Math.random() * -30 - 10,
    }));
    setSparkles(newSparkles);

    if (dismissTimer.current) clearTimeout(dismissTimer.current);
    dismissTimer.current = setTimeout(dismiss, 4000);
  };

  const dismiss = () => {
    setCasting(false);
    setSparkles([]);
    if (dismissTimer.current) { clearTimeout(dismissTimer.current); dismissTimer.current = null; }
  };

  return (
    <Box sx={{ position: "relative", display: "inline-flex", alignItems: "center" }} onMouseLeave={dismiss}>
      <Tooltip title={casting ? line : tooltip} arrow open={casting || undefined}>
        <IconButton
          size="small"
          onClick={cast}
          sx={{
            p: 0.25,
            color: casting ? "warning.main" : "action.disabled",
            transition: "color 0.3s, transform 0.3s",
            transform: casting ? "rotate(20deg) scale(1.3)" : "none",
            "&:hover": { color: "warning.main" },
          }}
        >
          <AutoFixHighIcon sx={{ fontSize: size }} />
        </IconButton>
      </Tooltip>
      {sparkles.map((s) => (
        <Box
          key={s.id}
          sx={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: 4,
            height: 4,
            borderRadius: "50%",
            bgcolor: "warning.main",
            pointerEvents: "none",
            opacity: 0,
            animation: "sparkle-fly 0.8s ease-out forwards",
            animationDelay: `${Math.random() * 0.3}s`,
            "--sx": `${s.x}px`,
            "--sy": `${s.y}px`,
            "@keyframes sparkle-fly": {
              "0%": { opacity: 1, transform: "translate(0, 0) scale(1)" },
              "100%": { opacity: 0, transform: `translate(var(--sx), var(--sy)) scale(0)` },
            },
          } as object}
        />
      ))}
    </Box>
  );
}
