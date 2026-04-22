import { useMemo } from "react";
import PillFilter from "@/components/common/PillFilter";
import type { RawTypeFacet } from "@/api/dsos";
import { displayDsoType } from "@/lib/dsoTypeNames";

export interface TypeFilterProps {
  /** Currently-selected raw ``obj_type`` codes (e.g. ``["G", "HII"]``). */
  value: string[];
  onChange: (codes: string[]) => void;
  /** Facet list from ``/api/dso/facets``'s ``raw_types``. Zero-count entries are filtered out. */
  options: RawTypeFacet[];
  label?: string;
  placeholder?: string;
}

/**
 * Thin adapter around ``PillFilter`` for OpenNGC ``obj_type`` codes.
 * Display labels come from ``displayDsoType`` (same map the grid's
 * Type column uses), so "G" renders as "Galaxy", "HII" as
 * "HII region", etc.
 */
export default function TypeFilter({
  value,
  onChange,
  options,
  label = "Object type",
  placeholder = "Click to add…",
}: TypeFilterProps) {
  const pillOptions = useMemo(
    () =>
      options.map((t) => ({
        code: t.code,
        displayName: displayDsoType(t.code),
        count: t.count,
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
