import { useCallback, useState } from "react";
import type { PlateSolveFilters } from "@/lib/plateSolveObjects";

const EMPTY_FILTERS: PlateSolveFilters = {
  catalogs: new Set<string>(),
  types: new Set<string>(),
  minSizeArcmin: 0,
};

function toggled(values: ReadonlySet<string>, value: string): Set<string> {
  const next = new Set(values);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export function usePlateSolveFilters() {
  const [filters, setFilters] = useState<PlateSolveFilters>(EMPTY_FILTERS);
  const toggleCatalog = useCallback(
    (catalog: string) =>
      setFilters((current) => ({ ...current, catalogs: toggled(current.catalogs, catalog) })),
    [],
  );
  const toggleType = useCallback(
    (type: string) =>
      setFilters((current) => ({ ...current, types: toggled(current.types, type) })),
    [],
  );
  const setMinimumSize = useCallback(
    (minSizeArcmin: number) => setFilters((current) => ({ ...current, minSizeArcmin })),
    [],
  );
  const clear = useCallback(() => setFilters(EMPTY_FILTERS), []);
  const activeCount =
    filters.catalogs.size + filters.types.size + (filters.minSizeArcmin > 0 ? 1 : 0);
  return { filters, toggleCatalog, toggleType, setMinimumSize, clear, activeCount };
}
