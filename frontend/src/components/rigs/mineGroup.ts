export const MINE_GROUP_LABEL = "My Equipment";
export const MY_SOFTWARE_LABEL = "My Software";

/**
 * Pre-process an option list so is_mine=true items appear both in a flat
 * "My Equipment" virtual group at the top AND in their regular group.
 * Returns a new array with duplicates. Caller's `groupBy` must check
 * `__mine_group` first.
 */
export function withMineGroup<
  T extends { is_mine?: boolean; manufacturer_name?: string; retired?: true },
>(
  options: readonly T[],
  label = MINE_GROUP_LABEL,
  order: (a: T, b: T) => number = (a, b) => {
    const ma = (a.manufacturer_name ?? "").toLowerCase();
    const mb = (b.manufacturer_name ?? "").toLowerCase();
    return ma.localeCompare(mb);
  },
): (T & { __mine_group?: string })[] {
  const sorted = [...options].sort((a, b) => {
    const retiredOrder = Number(Boolean(a.retired)) - Number(Boolean(b.retired));
    return retiredOrder || order(a, b);
  });
  const result: (T & { __mine_group?: string })[] = [];
  for (const opt of sorted) {
    if (opt.is_mine) {
      result.push({ ...opt, __mine_group: label });
    }
  }
  for (const opt of sorted) {
    result.push(opt);
  }
  return result;
}

export function mineOptionKey(option: {
  id: number;
  __mine_group?: string;
  retired?: true;
}): string {
  if (option.__mine_group) return `mine-${option.id}`;
  if (option.retired) return `retired-${option.id}`;
  return String(option.id);
}
