export interface SessionValues {
  gain: number | null;
  iso: number | null;
}

export type SessionValueColumn = "iso" | "gain";

/** Show only the capture-setting columns that contain a value in this rig group. */
export function sessionValueColumns(
  sessions: readonly SessionValues[],
): SessionValueColumn[] {
  const columns: SessionValueColumn[] = [];
  if (sessions.some((session) => session.iso != null)) columns.push("iso");
  if (sessions.some((session) => session.gain != null)) columns.push("gain");
  return columns;
}
