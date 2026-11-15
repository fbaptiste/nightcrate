import { ApiError, apiFetch } from "./client";

export type ActivityKind = "scan" | "frame_analysis" | "plate_solve" | "catalog" | "star_catalog";
export interface RunningActivity { kind: ActivityKind; label: string }
export interface ActivityResponse { running: RunningActivity[] }

export type InstallReservation =
  | { token: string }
  | { running: RunningActivity[] }
  | { installInProgress: true };

export const fetchActivity = () => apiFetch<ActivityResponse>("/app/activity");

export async function reserveInstall(): Promise<InstallReservation> {
  try {
    return await apiFetch<{ token: string }>("/app/install-reservation", { method: "POST" });
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 409) throw error;
    const detail = error.detail as { running?: RunningActivity[]; install_in_progress?: boolean };
    if (Array.isArray(detail?.running)) return { running: detail.running };
    if (detail?.install_in_progress) return { installInProgress: true };
    throw error;
  }
}

export const releaseInstall = (token: string) =>
  apiFetch<void>(`/app/install-reservation?token=${encodeURIComponent(token)}`, {
    method: "DELETE",
  });
