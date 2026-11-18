export interface InferredNote {
  label: "guessed" | "estimated" | "file time";
  title: string;
}

export function frameTypeNote(
  source: string | null | undefined,
  basis: string | null | undefined,
): InferredNote | null {
  return source === "auto" && (basis === "file_name" || basis === "folder_name")
    ? {
        label: "guessed",
        title: "Guessed from the file and folder names",
      }
    : null;
}

export function timeSourceNote(source: string | null | undefined): InferredNote | null {
  if (source === "estimated_project_zone") {
    return {
      label: "estimated",
      title: "Estimated: the file records no time zone, so the project location's zone was used",
    };
  }
  if (source === "estimated_computer_zone") {
    return {
      label: "estimated",
      title: "Estimated: the file records no time zone, so this computer's zone was used",
    };
  }
  if (source === "file_time") {
    return {
      label: "file time",
      title: "From the file's modification time",
    };
  }
  return null;
}

export interface FilterSuggestion {
  value: string;
  group: "This rig's filters" | "Bandpasses";
}

export function filterSuggestions(
  rigFilters: readonly string[],
  bandpasses: readonly string[],
): FilterSuggestion[] {
  const seen = new Set<string>();
  const suggestions: FilterSuggestion[] = [];
  for (const [values, group] of [
    [rigFilters, "This rig's filters"],
    [bandpasses, "Bandpasses"],
  ] as const) {
    for (const value of values) {
      const trimmed = value.trim();
      if (!trimmed || seen.has(trimmed)) continue;
      seen.add(trimmed);
      suggestions.push({ value: trimmed, group });
    }
  }
  return suggestions;
}

export function qualityLevelText(
  value: number | null | undefined,
  units: string | null | undefined,
): string {
  if (value == null) return "";
  if (units === "adu") return `${Math.round(value).toLocaleString("en-US")} ADU`;
  return value.toLocaleString("en-US", { maximumFractionDigits: 20, useGrouping: false });
}
