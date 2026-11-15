import type { Theme } from "@mui/material/styles";
import type { Stage } from "@/api/projects";

export function stageAppearance(stage: Stage) {
  return (theme: Theme) => {
    const dark = theme.palette.mode === "dark";
    const track = dark ? "#33363c" : "#e8e5e0";
    const outline = dark ? "rgba(255,255,255,0.13)" : "rgba(0,0,0,0.15)";
    const shared = { color: theme.palette.text.primary };
    if (stage === "capturing") {
      return { ...shared, bgcolor: theme.palette.primary.main, color: "#1f1a12" };
    }
    if (stage === "ready_to_process") {
      return { ...shared, bgcolor: "#2a8c82", color: "#fff" };
    }
    if (stage === "complete") {
      return { ...shared, bgcolor: dark ? "#2f6fc0" : "#1f63b0", color: "#fff" };
    }
    if (stage === "paused") {
      return {
        ...shared,
        background: `repeating-linear-gradient(135deg, ${track} 0 6px, transparent 6px 11px), ${theme.palette.background.paper}`,
        boxShadow: `inset 0 0 0 1.5px ${outline}`,
      };
    }
    if (stage === "abandoned") {
      return { ...shared, bgcolor: track, color: theme.palette.text.secondary };
    }
    return { ...shared, bgcolor: track, boxShadow: `inset 0 0 0 1.5px ${outline}` };
  };
}
