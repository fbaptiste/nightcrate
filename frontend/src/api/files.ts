import { apiFetch } from "./client";

export interface DirEntry {
  name: string;
  path: string;
}

export interface FileEntry {
  name: string;
  path: string;
  size: number;
}

export interface BrowseResult {
  path: string;
  parent: string | null;
  dirs: DirEntry[];
  files: FileEntry[];
}

export interface VolumeEntry {
  name: string;
  path: string;
}

export function fetchVolumes(): Promise<VolumeEntry[]> {
  return apiFetch<VolumeEntry[]>("/files/volumes");
}

export function browseDirectory(path: string): Promise<BrowseResult> {
  return apiFetch<BrowseResult>(`/files/browse?path=${encodeURIComponent(path)}`);
}

export interface HealthInfo {
  status: string;
  version: string;
}

export function fetchHealth(): Promise<HealthInfo> {
  return apiFetch<HealthInfo>("/health");
}
