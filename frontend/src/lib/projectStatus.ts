import type { ProjectStatus } from "@/api/projects";

export type ProjectStatusChipColor = "default" | "warning" | "info";
export type ProjectStatusThemeMode = "light" | "dark";

export interface ProjectStatusDisplay {
  label: string;
  description: string;
  chipColor: ProjectStatusChipColor;
  pillColor: Record<ProjectStatusThemeMode, string>;
}

export const PROJECT_STATUS_ORDER: ProjectStatus[] = [
  "active",
  "ready_to_process",
  "paused",
  "complete",
  "abandoned",
];

export const PROJECT_STATUS_DISPLAY: Record<ProjectStatus, ProjectStatusDisplay> = {
  active: {
    label: "Active",
    description: "Still capturing",
    chipColor: "default",
    pillColor: { light: "#6b6b6b", dark: "#8e8c88" },
  },
  ready_to_process: {
    label: "Ready to process",
    description: "Captured, waiting to be processed",
    chipColor: "default",
    pillColor: { light: "#17786d", dark: "#5cc6b9" },
  },
  paused: {
    label: "Paused",
    description: "On hold",
    chipColor: "warning",
    pillColor: { light: "#b85500", dark: "#f0a35e" },
  },
  complete: {
    label: "Complete",
    description: "Finished",
    chipColor: "info",
    pillColor: { light: "#1f63b0", dark: "#7fb2ea" },
  },
  abandoned: {
    label: "Abandoned",
    description: "Stopped for good",
    chipColor: "default",
    pillColor: { light: "#6b6b6b", dark: "#8e8c88" },
  },
};

export function projectStatusDisplay(
  status: string,
): ProjectStatusDisplay | undefined {
  return PROJECT_STATUS_DISPLAY[status as ProjectStatus];
}

export function projectStatusLabel(status: string): string {
  const known = projectStatusDisplay(status);
  if (known) return known.label;
  const words = status.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function projectStatusPillColor(
  status: string,
  mode: ProjectStatusThemeMode,
): string {
  return (
    projectStatusDisplay(status)?.pillColor[mode] ??
    PROJECT_STATUS_DISPLAY.active.pillColor[mode]
  );
}
