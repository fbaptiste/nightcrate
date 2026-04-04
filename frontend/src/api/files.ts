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

export interface ProjectEntry {
  name: string;
  path: string;
}

export interface ArchiveEntry {
  name: string;
  path: string;
}

export interface BrowseResult {
  path: string;
  parent: string | null;
  dirs: DirEntry[];
  files: FileEntry[];
  projects: ProjectEntry[];
  archives: ArchiveEntry[];
}

export interface ArchiveDirEntry {
  name: string;
}

export interface ArchiveFileEntry {
  name: string;
  size: number | null;
}

export interface ArchiveBrowseResult {
  path: string;
  subdir: string;
  parent: string | null;
  dirs: ArchiveDirEntry[];
  files: ArchiveFileEntry[];
}

export interface ProjectImageEntry {
  index: number;
  name: string;
  source: "referenced" | "embedded";
  file_path: string | null;
  filter: string | null;
  object: string | null;
  exposure: number | null;
  date_obs: string | null;
}

export interface ProjectBrowseResult {
  path: string;
  parent: string;
  images: ProjectImageEntry[];
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

export function browseProject(path: string): Promise<ProjectBrowseResult> {
  return apiFetch<ProjectBrowseResult>(`/files/browse-project?path=${encodeURIComponent(path)}`);
}

export function browseArchive(
  archivePath: string,
  subdir: string = ""
): Promise<ArchiveBrowseResult> {
  return apiFetch<ArchiveBrowseResult>(
    `/files/browse-archive?path=${encodeURIComponent(archivePath)}&subdir=${encodeURIComponent(subdir)}`
  );
}

export interface HealthInfo {
  status: string;
  version: string;
}

export function fetchHealth(): Promise<HealthInfo> {
  return apiFetch<HealthInfo>("/health");
}
