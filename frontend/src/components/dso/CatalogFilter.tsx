import { useMemo } from "react";
import PillFilter from "@/components/common/PillFilter";
import type { CatalogFacet } from "@/api/dsos";
import { displayCatalogName } from "@/lib/catalogNames";

export interface CatalogFilterProps {
  /** Currently-selected catalog codes (e.g., ``["messier", "ngc"]``). */
  value: string[];
  onChange: (codes: string[]) => void;
  /** Facet list from ``/api/dso/facets``. Zero-count entries are filtered out. */
  options: CatalogFacet[];
  label?: string;
  placeholder?: string;
}

/**
 * Thin adapter around ``PillFilter`` that maps ``CatalogFacet`` rows to
 * pill options via ``displayCatalogName``. Behavior + UX comes from
 * ``PillFilter``; this component just handles the naming and default
 * labels. See `PillFilter` for the shared pattern.
 */
export default function CatalogFilter({
  value,
  onChange,
  options,
  label = "Catalog",
  placeholder = "Click to add…",
}: CatalogFilterProps) {
  const pillOptions = useMemo(
    () =>
      options.map((c) => ({
        code: c.code,
        displayName: displayCatalogName(c.code),
        count: c.count,
      })),
    [options],
  );

  return (
    <PillFilter
      value={value}
      onChange={onChange}
      options={pillOptions}
      label={label}
      placeholder={placeholder}
    />
  );
}
