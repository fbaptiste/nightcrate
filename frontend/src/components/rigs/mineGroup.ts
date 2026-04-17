export const MINE_GROUP_LABEL = "My Equipment";

/**
 * Pre-process an option list so is_mine=true items appear both in a flat
 * "My Equipment" virtual group at the top AND in their regular group.
 * Returns a new array with duplicates. Caller's `groupBy` must check
 * `__mine_group` first.
 */
export function withMineGroup<T extends { is_mine?: boolean }>(
  options: T[],
): (T & { __mine_group?: string })[] {
  const result: (T & { __mine_group?: string })[] = [];
  for (const opt of options) {
    if (opt.is_mine) {
      result.push({ ...opt, __mine_group: MINE_GROUP_LABEL });
    }
  }
  for (const opt of options) {
    result.push(opt);
  }
  return result;
}
