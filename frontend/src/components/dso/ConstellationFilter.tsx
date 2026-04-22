import { useMemo } from "react";
import PillFilter from "@/components/common/PillFilter";
import type { ConstellationFacet } from "@/api/dsos";
import { displayConstellation } from "@/lib/constellations";

export interface ConstellationFilterProps {
  /** Currently-selected 3-letter IAU constellation codes (e.g., ``["Ori", "And"]``). */
  value: string[];
  onChange: (codes: string[]) => void;
  /** Facet list from ``/api/dso/facets``. Zero-count entries are filtered out. */
  options: ConstellationFacet[];
  label?: string;
  placeholder?: string;
}

/**
 * Thin adapter around ``PillFilter`` for IAU constellation codes.
 * Display labels come from ``displayConstellation`` (same helper the
 * grid's Constellation column uses), so "Ori" renders as "Orion",
 * "And" as "Andromeda", etc.
 */
export default function ConstellationFilter({
  value,
  onChange,
  options,
  label = "Constellation",
  placeholder = "Click to add…",
}: ConstellationFilterProps) {
  const pillOptions = useMemo(
    () =>
      options.map((c) => ({
        code: c.code,
        displayName: displayConstellation(c.code),
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
