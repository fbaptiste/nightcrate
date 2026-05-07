/**
 * Recent-files history for the PHD2 Analyzer. The actual list lives in the
 * `phd2_recent_files` table on the backend; the API client lives in
 * `@/api/phd2`. This module exposes a thin async wrapper that runs a
 * one-time migration of pre-existing browser-localStorage entries into
 * the database, plus the relative-time display helper.
 */
import {
  deleteRecentPhd2File,
  fetchRecentPhd2Files,
  recordRecentPhd2File,
  type RecentFile,
} from "@/api/phd2";

export type { RecentFile };

const LEGACY_STORAGE_KEY = "phd2.recentFiles";
const MIGRATED_FLAG_KEY = "phd2.recentFiles.migrated";

export async function getRecentFiles(): Promise<RecentFile[]> {
  await migrateLegacyOnce();
  return fetchRecentPhd2Files();
}

export async function addRecentFile(path: string): Promise<RecentFile[]> {
  try {
    await recordRecentPhd2File(path);
  } catch {
    // Network error — return current list anyway so UI stays consistent.
  }
  return fetchRecentPhd2Files();
}

export async function removeRecentFile(path: string): Promise<RecentFile[]> {
  try {
    await deleteRecentPhd2File(path);
  } catch {
    // ignore
  }
  return fetchRecentPhd2Files();
}

// Posts oldest-first so the most-recently-opened file ends up with the
// largest opened_at on the server. Sequential awaits are intentional —
// `datetime('now')` has 1-second resolution, so concurrent posts risk
// tying on timestamp; the route's `id DESC` tiebreaker preserves
// insertion order anyway, but the sequential pattern keeps the
// guarantee intact regardless. Idempotent via MIGRATED_FLAG_KEY.
async function migrateLegacyOnce(): Promise<void> {
  let raw: string | null;
  try {
    if (window.localStorage.getItem(MIGRATED_FLAG_KEY)) return;
    raw = window.localStorage.getItem(LEGACY_STORAGE_KEY);
  } catch {
    return;
  }
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        const valid = parsed.filter(
          (e): e is { path: string } =>
            typeof e === "object" &&
            e !== null &&
            typeof (e as { path: unknown }).path === "string",
        );
        for (let i = valid.length - 1; i >= 0; i--) {
          try {
            await recordRecentPhd2File(valid[i].path);
          } catch {
            // ignore individual failures
          }
        }
      }
    } catch {
      // corrupted localStorage — ignore
    }
  }
  try {
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
    window.localStorage.setItem(MIGRATED_FLAG_KEY, "1");
  } catch {
    // ignore
  }
}

export function formatRelativeTime(isoString: string): string {
  const then = new Date(isoString).getTime();
  if (Number.isNaN(then)) return "";
  const now = Date.now();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} min ago`;
  const thenDate = new Date(isoString);
  const nowDate = new Date();
  const msPerDay = 86_400_000;
  const thenMid = new Date(thenDate.getFullYear(), thenDate.getMonth(), thenDate.getDate()).getTime();
  const nowMid = new Date(nowDate.getFullYear(), nowDate.getMonth(), nowDate.getDate()).getTime();
  const dayDiff = Math.round((nowMid - thenMid) / msPerDay);
  if (dayDiff === 0) {
    return `today ${thenDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  }
  if (dayDiff === 1) return "yesterday";
  if (dayDiff < 7) return `${dayDiff} days ago`;
  return thenDate.toLocaleDateString([], { month: "short", day: "numeric" });
}
