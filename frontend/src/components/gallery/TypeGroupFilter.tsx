import PillFilter from "@/components/common/PillFilter";
import type { FacetCount } from "@/api/gallery";

interface Props {
  value: string[];
  onChange: (value: string[]) => void;
  options: FacetCount[];
}

export default function TypeGroupFilter({ value, onChange, options }: Props) {
  const pillOptions = options.map((option) => ({
    code: option.code,
    displayName: option.code,
    count: option.count,
  }));
  return (
    <PillFilter
      value={value}
      onChange={onChange}
      label="Object type"
      placeholder="Any type"
      options={pillOptions}
    />
  );
}
