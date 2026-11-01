import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface InstalledCatalog {
  version: string;
  size_bytes: number;
  installed_at: string;
  source: "download" | "import";
  uncompressed_sha256: string;
}

export interface SourceStatus {
  version: string;
  download_bytes: number;
  unpacked_bytes: number;
  doi: string;
  licence: string;
  gaia_licence: string;
  attribution: string;
}

export interface RigCoverage {
  id: number;
  name: string;
  field_deg: number;
}

export interface RangeStatus {
  id: string;
  name: string;
  recommended: boolean;
  min_deg: number;
  max_deg: number;
  state: "not_built" | "waiting" | "building" | "built" | "needs_rebuild";
  progress: number | null;
  size_bytes: number;
  size_is_estimate: boolean;
  build_memory_bytes: number;
  rigs: RigCoverage[];
}

export interface StarOperation {
  kind: "download" | "import" | "build" | "remove";
  state: "running" | "done" | "failed" | "cancelled";
  phase:
    | "downloading"
    | "verifying"
    | "unpacking"
    | "copying"
    | "building"
    | "publishing"
    | "removing";
  bytes_done: number;
  bytes_total: number;
  speed_bytes_per_s: number | null;
  ranges: string[];
  current_range: string | null;
  range_progress: Record<string, number>;
  progress: number | null;
  message: string | null;
}

export interface StarCatalogStatus {
  installed: InstalledCatalog | null;
  source: SourceStatus;
  operation: StarOperation | null;
  ranges: RangeStatus[];
  total_bytes_used: number;
  free_bytes: number;
}

const statusKey = ["star-catalog-status"] as const;

export function useStarCatalogStatus(enabled = true) {
  return useQuery({
    queryKey: statusKey,
    queryFn: () => apiFetch<StarCatalogStatus>("/admin/star-catalog/status"),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.operation?.state === "running" ? 1_000 : false,
  });
}

function useStatusMutation<T>(mutationFn: (value: T) => Promise<StarOperation>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: statusKey }),
  });
}

export function useDownloadStarCatalog() {
  return useStatusMutation<void>(() =>
    apiFetch<StarOperation>("/admin/star-catalog/download", { method: "POST" }),
  );
}

export function useImportStarCatalog() {
  return useStatusMutation<string>((path) =>
    apiFetch<StarOperation>("/admin/star-catalog/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    }),
  );
}

export function useCancelStarCatalogOperation() {
  return useStatusMutation<void>(() =>
    apiFetch<StarOperation>("/admin/star-catalog/cancel", { method: "POST" }),
  );
}

export function useBuildStarCatalogRanges() {
  return useStatusMutation<string[]>((rangeIds) =>
    apiFetch<StarOperation>("/admin/star-catalog/ranges/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ range_ids: rangeIds }),
    }),
  );
}

export function useDeleteStarCatalogRange() {
  return useStatusMutation<string>((rangeId) =>
    apiFetch<StarOperation>(`/admin/star-catalog/ranges/${encodeURIComponent(rangeId)}`, {
      method: "DELETE",
    }),
  );
}

export function useDeleteStarCatalog() {
  return useStatusMutation<void>(() =>
    apiFetch<StarOperation>("/admin/star-catalog/", { method: "DELETE" }),
  );
}
