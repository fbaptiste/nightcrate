import { apiFetch } from "./client";
import { fetchHealth as _fetchHealth } from "./files";

export interface AppInfo {
  config_file: string;
  app_data_dir: string;
  backend_root: string;
  seed_data_dir: string;
  python_version: string;
}

export interface DatabaseInfo {
  path: string;
  name: string;
  size_bytes: number | null;
  available: boolean;
}

export interface AdminStatus {
  db_configured: boolean;
  active_db: DatabaseInfo | null;
  known_databases: DatabaseInfo[];
}

export interface BrowseResult {
  path: string;
  dirs: { name: string; path: string }[];
  files: { name: string; path: string; size: number }[];
}

export interface HealthResponse {
  status: string;
  version: string;
  db_configured: boolean;
}

export const fetchAdminInfo = () => apiFetch<AppInfo>("/admin/info");

export const fetchAdminStatus = () => apiFetch<AdminStatus>("/admin/status");

export const createDatabase = (data: { path: string; name: string }) =>
  apiFetch<DatabaseInfo>("/admin/database/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const addExistingDatabase = (data: { path: string; name: string }) =>
  apiFetch<DatabaseInfo>("/admin/database/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const setupDatabase = (data: { path: string; name: string }) =>
  apiFetch<DatabaseInfo>("/admin/database/setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const activateDatabase = (path: string) =>
  apiFetch<DatabaseInfo>("/admin/database/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });

export const removeDatabase = (path: string, deleteFile = false) =>
  apiFetch<{ ok: boolean }>(
    `/admin/database${deleteFile ? "?delete_file=true" : ""}`,
    {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    },
  );

export const browseForDatabase = (path = "~") =>
  apiFetch<BrowseResult>(`/admin/browse?path=${encodeURIComponent(path)}`);

export interface Shortcuts {
  home: string;
  documents: string;
  app_data: string;
}

export const fetchShortcuts = () => apiFetch<Shortcuts>("/admin/shortcuts");

export const createFolder = (path: string) =>
  apiFetch<{ path: string }>("/admin/mkdir", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });

export const fetchHealth = () => _fetchHealth() as Promise<HealthResponse>;
