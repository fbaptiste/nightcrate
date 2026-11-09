export type RetainedOption<T> = T & { retired?: true };

export function keepRetiredSelected<T extends { id: number }>(
  activeOptions: readonly T[],
  selectedIds: readonly (number | null | undefined)[],
  createOption: (id: number) => T | null,
): RetainedOption<T>[] {
  const result: RetainedOption<T>[] = [...activeOptions];
  const included = new Set(activeOptions.map((option) => option.id));

  for (const id of selectedIds) {
    if (id == null || included.has(id)) continue;
    const option = createOption(id);
    if (!option) continue;
    result.push({ ...option, retired: true });
    included.add(id);
  }
  return result;
}

export function retainedGroup(option: { retired?: true }, regularGroup: string): string {
  return option.retired ? "Retired" : regularGroup;
}

export function retainedLabel(option: { retired?: true }, regularLabel: string, name: string): string {
  return option.retired ? `${name} (retired)` : regularLabel;
}
