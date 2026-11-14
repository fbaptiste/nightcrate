const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export function formatMonthDay(month: number, day: number): string {
  return `${MONTHS[month - 1]} ${day}`;
}

export function headerSubtitle(targetLabels: string[], constellationName: string): string {
  if (!targetLabels.length) return `Centred in ${constellationName}`;
  if (targetLabels.length === 1) return `${targetLabels[0]} in ${constellationName}`;
  if (targetLabels.length === 2) return `${targetLabels[0]} and ${targetLabels[1]} in ${constellationName}`;
  return `${targetLabels.length} targets in ${constellationName}`;
}

export function pictureLabel(projectName: string): string {
  return projectName.length > 32 ? `${projectName.slice(0, 31)}…` : projectName;
}
