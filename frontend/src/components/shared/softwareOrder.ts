const RIG_CATEGORY_ORDER = [
  "capture",
  "guiding",
  "plate_solving",
  "planetarium",
  "utility",
  "other",
  "processing",
] as const;

type SoftwareLike = { name: string; category: string };

export function orderSoftwareOptions<T extends SoftwareLike>(
  options: readonly T[],
  kind: "rig" | "project",
): T[] {
  const categories =
    kind === "project"
      ? ["processing", ...RIG_CATEGORY_ORDER.filter((category) => category !== "processing")]
      : [...RIG_CATEGORY_ORDER];
  const rank = new Map(categories.map((category, index) => [category, index]));

  return [...options].sort((a, b) => {
    const categoryOrder =
      (rank.get(a.category) ?? categories.length) -
      (rank.get(b.category) ?? categories.length);
    if (categoryOrder !== 0) return categoryOrder;
    return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
  });
}
