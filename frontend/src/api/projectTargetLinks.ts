import { useQuery, type QueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { ImagingRun } from "./gallery";

export interface ProjectTargetLink {
  dso_id: number;
  project_id: number;
  name: string;
  status: string;
  first_date: string | null;
  last_date: string | null;
  nights: number;
  imaging_runs: ImagingRun[];
}

const PROJECT_TARGET_LINKS_KEY = ["project-target-links"] as const;

async function fetchProjectTargetLinks(): Promise<ProjectTargetLink[]> {
  return apiFetch<ProjectTargetLink[]>("/project-target-links");
}

// Module-level so TanStack Query reruns it only when the data changes. An
// inline select returns a new Map on every render, which made the Planner
// re-render in a loop ("Maximum update depth exceeded").
function groupLinksByDso(links: ProjectTargetLink[]): Map<number, ProjectTargetLink[]> {
  const byDso = new Map<number, ProjectTargetLink[]>();
  for (const link of links) {
    const projectLinks = byDso.get(link.dso_id) ?? [];
    projectLinks.push(link);
    byDso.set(link.dso_id, projectLinks);
  }
  return byDso;
}

export function useProjectTargetLinks(enabled: boolean) {
  return useQuery({
    queryKey: PROJECT_TARGET_LINKS_KEY,
    queryFn: fetchProjectTargetLinks,
    enabled,
    select: groupLinksByDso,
  });
}

export function invalidateProjectLinks(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({ queryKey: PROJECT_TARGET_LINKS_KEY });
}
