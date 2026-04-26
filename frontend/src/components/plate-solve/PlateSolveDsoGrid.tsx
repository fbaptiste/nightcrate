import { useCallback, useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TableSortLabel from "@mui/material/TableSortLabel";

import type { AnnotatedDso } from "@/api/plateSolve";
import { formatDistance } from "@/lib/distanceFormat";
import { monoFontFamily } from "@/theme/theme";

type SortKey = "primary_designation" | "common_name" | "type_group" | "maj_axis_arcmin" | "distance_pc";
type SortDir = "asc" | "desc";

interface Props {
  dsos: AnnotatedDso[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

const cellSx = { fontSize: "0.75rem", py: 0.5, px: 1, whiteSpace: "nowrap" } as const;
const headerSx = { ...cellSx, fontWeight: 600 } as const;

export function PlateSolveDsoGrid({ dsos, selectedId, onSelect }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("maj_axis_arcmin");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const rowRefs = useRef<Map<number, HTMLTableRowElement>>(new Map());

  useEffect(() => {
    if (selectedId != null) {
      const el = rowRefs.current.get(selectedId);
      el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [selectedId]);

  const handleSort = useCallback((key: SortKey) => {
    setSortKey((prev) => {
      if (prev === key) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        return key;
      }
      setSortDir(key === "primary_designation" || key === "common_name" ? "asc" : "desc");
      return key;
    });
  }, []);

  const sorted = [...dsos].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = typeof av === "string" ? av.localeCompare(bv as string) : (av as number) - (bv as number);
    return sortDir === "asc" ? cmp : -cmp;
  });

  return (
    <TableContainer component={Box} sx={{ maxHeight: "100%", overflow: "auto" }}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            <SortHeader label="Designation" field="primary_designation" sortKey={sortKey} sortDir={sortDir} onClick={handleSort} />
            <SortHeader label="Name" field="common_name" sortKey={sortKey} sortDir={sortDir} onClick={handleSort} />
            <SortHeader label="Type" field="type_group" sortKey={sortKey} sortDir={sortDir} onClick={handleSort} />
            <SortHeader label="Size (′)" field="maj_axis_arcmin" sortKey={sortKey} sortDir={sortDir} onClick={handleSort} />
            <SortHeader label="Distance" field="distance_pc" sortKey={sortKey} sortDir={sortDir} onClick={handleSort} />
          </TableRow>
        </TableHead>
        <TableBody>
          {sorted.map((dso) => {
            const dist = dso.distance_pc != null ? formatDistance(dso.distance_pc) : null;
            return (
              <TableRow
                key={dso.id}
                ref={(el) => {
                  if (el) rowRefs.current.set(dso.id, el);
                  else rowRefs.current.delete(dso.id);
                }}
                hover
                selected={dso.id === selectedId}
                onClick={() => onSelect(dso.id)}
                sx={{ cursor: "pointer" }}
              >
                <TableCell sx={{ ...cellSx, fontFamily: monoFontFamily }}>{dso.primary_designation}</TableCell>
                <TableCell sx={cellSx}>{dso.common_name ?? ""}</TableCell>
                <TableCell sx={cellSx}>{dso.type_group}</TableCell>
                <TableCell sx={{ ...cellSx, fontFamily: monoFontFamily }}>
                  {dso.maj_axis_arcmin != null ? dso.maj_axis_arcmin.toFixed(1) : ""}
                </TableCell>
                <TableCell sx={{ ...cellSx, fontFamily: monoFontFamily }}>
                  {dist ? dist.primary : ""}
                </TableCell>
              </TableRow>
            );
          })}
          {sorted.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} sx={{ ...cellSx, color: "text.secondary", textAlign: "center" }}>
                No objects match the current filters.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function SortHeader({
  label,
  field,
  sortKey,
  sortDir,
  onClick,
}: {
  label: string;
  field: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onClick: (key: SortKey) => void;
}) {
  return (
    <TableCell sx={headerSx}>
      <TableSortLabel
        active={sortKey === field}
        direction={sortKey === field ? sortDir : "asc"}
        onClick={() => onClick(field)}
        sx={{ fontSize: "inherit" }}
      >
        {label}
      </TableSortLabel>
    </TableCell>
  );
}
