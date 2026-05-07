/**
 * Recent-files history for the PHD2 Analyzer — backed by the
 * phd2_recent_files table on the backend (POST/GET/DELETE
 * /api/phd2/recent). On first call after the upgrade, any pre-existing
 * localStorage entries are migrated into the database and localStorage is
 * cleared. Mirrors the image-analyzer recent-files pattern.
 */

const LEGACY_STORAGE_KEY = "phd2.recentFiles";
const MIGRATED_FLAG_KEY = "phd2.recentFiles.migrated";

export interface RecentFile {
  path: string;
  openedAt: string;
}

interface RecentFileApi {
  path: string;
  opened_at: string;
}

function fromApi(r: RecentFileApi): RecentFile {
  return { path: r.path, openedAt: r.opened_at };
}

async function fetchList(): Promise<RecentFile[]> {
  try {
    const r = await fetch("/api/phd2/recent");
    if (!r.ok) return [];
    const data: RecentFileApi[] = await r.json();
    return data.map(fromApi);
  } catch {
    return [];
  }
}

export async function getRecentFiles(): Promise<RecentFile[]> {
  await migrateLegacyOnce();
  return fetchList();
}

export async function addRecentFile(path: string): Promise<RecentFile[]> {
  try {
    await fetch(`/api/phd2/recent?path=${encodeURIComponent(path)}`, {
      method: "POST",
    });
  } catch {
    // Network error — return current list anyway so UI stays consistent.
  }
  return fetchList();
}

export async function removeRecentFile(path: string): Promise<RecentFile[]> {
  try {
    await fetch(`/api/phd2/recent?path=${encodeURIComponent(path)}`, {
      method: "DELETE",
    });
  } catch {
    // Network error — return current list anyway.
  }
  return fetchList();
}

// One-time migration of pre-existing localStorage entries into the
// database. Posts oldest-first so the most recently opened file ends up
// with the most recent opened_at on the server (relative ordering is
// preserved; absolute timestamps reset to "now"). Idempotent — guarded
// by a localStorage flag, so subsequent calls are no-ops.
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
            await fetch(
              `/api/phd2/recent?path=${encodeURIComponent(valid[i].path)}`,
              { method: "POST" },
            );
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
