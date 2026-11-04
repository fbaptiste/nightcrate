import { useMemo } from "react";
import PillFilter from "@/components/common/PillFilter";
import type { RawTypeFacet } from "@/api/dsos";
import { displayDsoType, filterTypeCode } from "@/lib/dsoTypeNames";

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
 * Type column uses). Filter-equivalent raw codes are normalized to
 * one option and selected chip.
 */
export default function TypeFilter({
  value,
  onChange,
  options,
  label = "Object type",
  placeholder = "Click to add…",
}: TypeFilterProps) {
  const normalizedValue = useMemo(
    () => [...new Set(value.map(filterTypeCode))],
    [value],
  );

  const pillOptions = useMemo(
    () => {
      const normalized = new Map<string, number>();
      for (const option of options) {
        const code = filterTypeCode(option.code);
        normalized.set(code, (normalized.get(code) ?? 0) + option.count);
      }
      return [...normalized].map(([code, count]) => ({
        code,
        displayName: displayDsoType(code),
        count,
      }));
    },
    [options],
  );

  return (
    <PillFilter
      value={normalizedValue}
      onChange={(codes) => onChange([...new Set(codes.map(filterTypeCode))])}
      options={pillOptions}
      label={label}
      placeholder={placeholder}
    />
  );
}
