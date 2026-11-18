import { apiFetch } from "./client";

export type NoticeId = "app" | "openngc" | "mgc50_age" | "wikidata_age" | "wikidata_query";
export type NoticeAction = "later" | "skip" | "remind";

export interface UpdateNotice {
  id: NoticeId;
  version: string | null;
  current_version: string | null;
  published_at: string | null;
  notes: string[];
  release_url: string | null;
  installable: boolean;
  install_blocked: string | null;
  latest_tag: string | null;
  installed_tag: string | null;
  downloaded_at: string | null;
}

export interface UpdatesStatus {
  check_automatically: boolean | null;
  install_kind: "installed" | "source";
  current_version: string;
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  check_due: boolean;
  skipped_version: string | null;
  notices: UpdateNotice[];
  updated_from: string | null;
  backup_taken: boolean;
}

export const fetchUpdates = () => apiFetch<UpdatesStatus>("/updates");
export const checkForUpdates = () => apiFetch<UpdatesStatus>("/updates/check", { method: "POST" });
export const setCheckAutomatically = (value: boolean) =>
  apiFetch<UpdatesStatus>("/updates/preferences", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ check_automatically: value }),
  });
export const dismissNotice = (id: NoticeId, action: NoticeAction) =>
  apiFetch<UpdatesStatus>(`/updates/notices/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
export const clearSkippedVersion = () =>
  apiFetch<void>("/updates/skipped-version", { method: "DELETE" });
export const markVersionSeen = () =>
  apiFetch<void>("/updates/seen-version", { method: "POST" });
