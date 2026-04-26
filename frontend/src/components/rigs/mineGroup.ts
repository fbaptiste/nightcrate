export const MINE_GROUP_LABEL = "My Equipment";

/**
 * Pre-process an option list so is_mine=true items appear both in a flat
 * "My Equipment" virtual group at the top AND in their regular group.
 * Returns a new array with duplicates. Caller's `groupBy` must check
 * `__mine_group` first.
 */
export function withMineGroup<T extends { is_mine?: boolean; manufacturer_name?: string }>(
  options: T[],
): (T & { __mine_group?: string })[] {
  const sorted = [...options].sort((a, b) => {
    const ma = (a.manufacturer_name ?? "").toLowerCase();
    const mb = (b.manufacturer_name ?? "").toLowerCase();
    return ma.localeCompare(mb);
  });
  const result: (T & { __mine_group?: string })[] = [];
  for (const opt of sorted) {
    if (opt.is_mine) {
      result.push({ ...opt, __mine_group: MINE_GROUP_LABEL });
    }
  }
  for (const opt of sorted) {
    result.push(opt);
  }
  return result;
}
