/**
 * Gantt-style calendar view for the wishlist.
 *
 * Filters by location + rig. Only shows targets that have date ranges.
 * Each row: flat-color bars for planned date ranges, moon phase markers,
 * hover crosshair with tooltip showing target + range details, positive
 * stops at range boundaries.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import * as d3 from "d3";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import { useTheme } from "@mui/material/styles";
import { fetchLocations, type Location } from "@/api/locations";
import { fetchHorizons, type Horizon } from "@/api/horizons";
import { fetchRigs, type Rig } from "@/api/rigs";
import { useCalendarData, reorderSections, type CalendarResponse, type DateRangeOut } from "@/api/wishlist";
import { usePlannerStore } from "@/stores/plannerStore";
import { RIG_ORANGE } from "@/lib/rigColors";

const MARGIN = { top: 60, right: 10, bottom: 20, left: 120 };
const SECTION_BAR_W = 24;
const ROW_HEIGHT = 32;
const MIN_SECTION_HEIGHT = 80;
const SECTION_GAP = 12;
const MIN_HEIGHT = 200;
const MONTH_COL_MIN_PX = 80;

const SECTION_COLORS = ["#2196f3", "#ff9800", "#00bcd4"];
const REF_YEAR = 2000;

function toRefDate(iso: string): Date {
  const d = new Date(`${iso}T00:00:00Z`);
  return new Date(Date.UTC(REF_YEAR, d.getUTCMonth(), d.getUTCDate()));
}

function toRefNow(): Date {
  const d = new Date();
  return new Date(Date.UTC(REF_YEAR, d.getUTCMonth(), d.getUTCDate()));
}
const SNAP_PX = 8;

interface HoverInfo {
  xPx: number;
  dateLabel: string;
  target: string | null;
  rangeLabel: string | null;
  isSnapped: boolean;
}

export default function WishlistCalendarView({
  onEditTarget,
}: {
  onEditTarget?: (dsoId: number, planId: number) => void;
}) {
  const theme = useTheme();
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);

  const storeLocationId = usePlannerStore((s) => s.calendarLocationId);
  const storeHorizonId = usePlannerStore((s) => s.calendarHorizonId);
  const storeRigId = usePlannerStore((s) => s.calendarRigId);
  const setStoreLocationId = usePlannerStore((s) => s.setCalendarLocationId);
  const setStoreHorizonId = usePlannerStore((s) => s.setCalendarHorizonId);
  const setStoreRigId = usePlannerStore((s) => s.setCalendarRigId);
  const locationId = storeLocationId ?? "";
  const horizonId = storeHorizonId ?? "";
  const rigId = storeRigId ?? "";
  const setLocationId = (id: number | "") => setStoreLocationId(id === "" ? null : id);
  const setHorizonId = (id: number | "") => setStoreHorizonId(id === "" ? null : id);
  const setRigId = (id: number | "") => setStoreRigId(id === "" ? null : id);

  const locationsQuery = useQuery({
    queryKey: ["locations"],
    queryFn: fetchLocations,
    staleTime: 5 * 60_000,
  });

  const horizonsQuery = useQuery({
    queryKey: ["horizons", locationId],
    queryFn: () => fetchHorizons(locationId as number),
    enabled: locationId !== "",
    staleTime: 5 * 60_000,
  });

  const rigsQuery = useQuery({
    queryKey: ["rigs"],
    queryFn: () => fetchRigs(true),
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (locationId === "" && locationsQuery.data) {
      const def = locationsQuery.data.find((l) => l.is_default);
      if (def) setLocationId(def.id);
    }
  }, [locationId, locationsQuery.data, setLocationId]);

  useEffect(() => {
    if (locationId !== "" && horizonId === "" && horizonsQuery.data) {
      const def = horizonsQuery.data.find((h: Horizon) => h.is_default);
      if (def) setHorizonId(def.id);
    }
  }, [locationId, horizonId, horizonsQuery.data, setHorizonId]);

  useEffect(() => {
    if (rigId === "" && rigsQuery.data) {
      const def = rigsQuery.data.find((r) => r.is_default);
      if (def) setRigId(def.id);
    }
  }, [rigId, rigsQuery.data, setRigId]);

  const calendarQuery = useCalendarData({
    locationId: locationId as number,
    horizonId: horizonId as number,
    rigId: rigId as number,
  });

  const data = calendarQuery.data;
  const isDark = theme.palette.mode === "dark";
  const locations: Location[] = locationsQuery.data ?? [];
  const horizons: Horizon[] = horizonsQuery.data ?? [];
  const rigs: Rig[] = rigsQuery.data ?? [];
  const selectionComplete = locationId !== "" && horizonId !== "" && rigId !== "";

  return (
    <Stack spacing={2} sx={{ pt: 1 }}>
      <Stack direction="row" gap={2}>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel>Location</InputLabel>
          <Select
            value={locationId}
            label="Location"
            onChange={(e) => setLocationId(e.target.value as number)}
          >
            {locations.map((loc) => (
              <MenuItem key={loc.id} value={loc.id}>{loc.name}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 200 }} disabled={locationId === ""}>
          <InputLabel>Horizon</InputLabel>
          <Select
            value={horizonId}
            label="Horizon"
            onChange={(e) => setHorizonId(e.target.value as number)}
          >
            {horizons.map((hz) => (
              <MenuItem key={hz.id} value={hz.id}>
                {hz.name}
                {hz.type === "artificial" && hz.flat_altitude_deg != null
                  ? ` (${hz.flat_altitude_deg}°)`
                  : ""}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel>Rig</InputLabel>
          <Select
            value={rigId}
            label="Rig"
            onChange={(e) => setRigId(e.target.value as number)}
          >
            {rigs.map((rig) => (
              <MenuItem key={rig.id} value={rig.id}>{rig.name}</MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>

      {!selectionComplete ? (
        <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
          Select a location, horizon, and rig to view the calendar.
        </Typography>
      ) : calendarQuery.isLoading || calendarQuery.isFetching ? (
        <Box sx={{ py: 4, textAlign: "center" }}>
          <CircularProgress size={28} />
        </Box>
      ) : calendarQuery.isError ? (
        <Typography color="error" sx={{ py: 4, textAlign: "center" }}>
          Failed to load calendar data. Try again later.
        </Typography>
      ) : data && data.targets.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
          No targets with date ranges for this location, horizon, and rig combo.
        </Typography>
      ) : data ? (
        <CalendarChart
          data={data}
          wrapperRef={wrapperRef}
          isDark={isDark}
          hover={hover}
          setHover={setHover}
          onEditTarget={onEditTarget}
        />
      ) : null}
    </Stack>
  );
}


function CalendarChart({
  data,
  wrapperRef,
  isDark,
  hover,
  setHover,
  onEditTarget,
}: {
  data: CalendarResponse;
  wrapperRef: React.RefObject<HTMLDivElement | null>;
  isDark: boolean;
  hover: HoverInfo | null;
  setHover: (h: HoverInfo | null) => void;
  onEditTarget?: (dsoId: number, planId: number) => void;
}) {
  const queryClient = useQueryClient();
  const [moonTip, setMoonTip] = useState<{
    x: number; y: number; phase: string; date: string;
  } | null>(null);

  const reorderMutation = useMutation({
    mutationFn: reorderSections,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["wishlist"] });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
    },
  });

  const fmtLabel = (t: { primary_designation: string; common_name: string | null }) =>
    t.common_name ? `${t.primary_designation} (${t.common_name})` : t.primary_designation;

  const hasSections = data.sections.length > 0 &&
    data.targets.some((t) => t.section_id != null);
  const sectionBarW = hasSections ? SECTION_BAR_W : 0;

  const sectionGroups = useMemo(() => {
    const groups: {
      id: number | null; name: string; startRow: number; count: number;
      yStart: number; height: number;
    }[] = [];
    let currentId: number | null | undefined = undefined;
    for (let i = 0; i < data.targets.length; i++) {
      const t = data.targets[i];
      if (t.section_id !== currentId) {
        groups.push({
          id: t.section_id,
          name: t.section_name ?? "General",
          startRow: i,
          count: 1,
          yStart: 0,
          height: 0,
        });
        currentId = t.section_id;
      } else {
        groups[groups.length - 1].count++;
      }
    }
    if (hasSections) {
      let yOffset = 0;
      for (const g of groups) {
        g.yStart = yOffset;
        g.height = Math.max(MIN_SECTION_HEIGHT, g.count * ROW_HEIGHT);
        yOffset += g.height + SECTION_GAP;
      }
    }
    return groups;
  }, [data.targets, hasSections]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );
  const namedSectionIds = useMemo(
    () => sectionGroups.filter((g) => g.id !== null).map((g) => g.id!),
    [sectionGroups],
  );
  const handleSectionDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIdx = namedSectionIds.indexOf(active.id as number);
    const newIdx = namedSectionIds.indexOf(over.id as number);
    if (oldIdx === -1 || newIdx === -1) return;
    const reordered = arrayMove(namedSectionIds, oldIdx, newIdx);
    reorderMutation.mutate(reordered);
  };

  const maxLabelLen = useMemo(
    () => Math.max(...data.targets.map((t) => fmtLabel(t).length), 6),
    [data.targets],
  );
  const labelMargin = Math.max(MARGIN.left, maxLabelLen * 7 + 8);
  const leftMargin = labelMargin;
  const innerW = 12 * MONTH_COL_MIN_PX;
  const svgWidth = leftMargin + innerW + MARGIN.right;

  const rowPositions = useMemo(() => {
    const positions: { y: number; h: number }[] = [];
    if (!hasSections || sectionGroups.length === 0) {
      for (let i = 0; i < data.targets.length; i++) {
        positions.push({ y: i * ROW_HEIGHT, h: ROW_HEIGHT });
      }
    } else {
      for (const sg of sectionGroups) {
        const rowH = sg.count > 0 ? sg.height / sg.count : ROW_HEIGHT;
        const contentH = sg.count * rowH;
        const vPad = (sg.height - contentH) / 2;
        for (let i = 0; i < sg.count; i++) {
          positions.push({
            y: sg.yStart + vPad + i * rowH,
            h: rowH,
          });
        }
      }
    }
    return positions;
  }, [data.targets.length, hasSections, sectionGroups]);

  const innerH = hasSections && sectionGroups.length > 0
    ? sectionGroups[sectionGroups.length - 1].yStart + sectionGroups[sectionGroups.length - 1].height
    : data.targets.length * ROW_HEIGHT;
  const chartHeight = Math.max(MIN_HEIGHT, MARGIN.top + innerH + MARGIN.bottom + 1);

  const rowY = (idx: number) => rowPositions[idx]?.y ?? 0;
  const rowH = (idx: number) => rowPositions[idx]?.h ?? ROW_HEIGHT;

  const monthDates = useMemo(
    () => Array.from({ length: 12 }, (_, i) => new Date(Date.UTC(REF_YEAR, i, 1))),
    [],
  );
  const endDate = useMemo(
    () => new Date(Date.UTC(REF_YEAR + 1, 0, 1)),
    [],
  );

  const x = useMemo(
    () => d3.scaleTime().domain([monthDates[0], endDate]).range([0, innerW]),
    [monthDates, endDate, innerW],
  );

  const snapXPositions = useMemo(() => {
    const snaps: { xPx: number; targetIdx: number; rangeIdx: number; edge: "start" | "end" }[] = [];
    data.targets.forEach((target, tIdx) => {
      target.date_ranges.forEach((dr, rIdx) => {
        const rs = toRefDate(dr.start_date);
        const re = toRefDate(dr.end_date);
        if (rs <= re) {
          snaps.push({ xPx: x(rs), targetIdx: tIdx, rangeIdx: rIdx, edge: "start" });
          snaps.push({ xPx: x(re), targetIdx: tIdx, rangeIdx: rIdx, edge: "end" });
        } else {
          snaps.push({ xPx: x(rs), targetIdx: tIdx, rangeIdx: rIdx, edge: "start" });
          snaps.push({ xPx: x(new Date(Date.UTC(REF_YEAR, 11, 31))), targetIdx: tIdx, rangeIdx: rIdx, edge: "end" });
          snaps.push({ xPx: x(new Date(Date.UTC(REF_YEAR, 0, 1))), targetIdx: tIdx, rangeIdx: rIdx, edge: "start" });
          snaps.push({ xPx: x(re), targetIdx: tIdx, rangeIdx: rIdx, edge: "end" });
        }
      });
    });
    return snaps;
  }, [data.targets, x]);

  const formatDate = (d: Date) =>
    d.toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });


  const todayXPx = x(toRefNow());

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const mx = e.clientX - rect.left - leftMargin;
    const my = e.clientY - rect.top - MARGIN.top;

    if (mx < 0 || mx > innerW || my < 0 || my > innerH) {
      setHover(null);
      return;
    }

    let rowIdx = -1;
    for (let i = 0; i < rowPositions.length; i++) {
      const rp = rowPositions[i];
      if (my >= rp.y && my < rp.y + rp.h) { rowIdx = i; break; }
    }
    const target = rowIdx >= 0 && rowIdx < data.targets.length ? data.targets[rowIdx] : null;

    let snapX = mx;
    let isSnapped = false;

    for (const snap of snapXPositions) {
      if (snap.targetIdx === rowIdx && Math.abs(mx - snap.xPx) <= SNAP_PX) {
        snapX = snap.xPx;
        isSnapped = true;
        break;
      }
    }

    const hoverDate = x.invert(snapX);

    let rangeLabel: string | null = null;
    let targetName: string | null = null;
    if (target) {
      targetName = fmtLabel(target);
      for (const dr of target.date_ranges) {
        const rs = toRefDate(dr.start_date);
        const re = toRefDate(dr.end_date);
        if (rs <= re) {
          if (hoverDate >= rs && hoverDate <= re) {
            rangeLabel = `${formatDate(rs)} – ${formatDate(re)}`;
            break;
          }
        } else {
          const yearEnd = new Date(Date.UTC(REF_YEAR, 11, 31));
          const yearStart = new Date(Date.UTC(REF_YEAR, 0, 1));
          if (hoverDate >= rs && hoverDate <= yearEnd) {
            rangeLabel = `${formatDate(rs)} – ${formatDate(re)}`;
            break;
          }
          if (hoverDate >= yearStart && hoverDate <= re) {
            rangeLabel = `${formatDate(rs)} – ${formatDate(re)}`;
            break;
          }
        }
      }
    }

    setHover({
      xPx: snapX,
      dateLabel: formatDate(hoverDate),
      target: targetName,
      rangeLabel,
      isSnapped,
    });
  };

  const rowSectionColor = useMemo(() => {
    const colors: string[] = [];
    if (!hasSections || sectionGroups.length === 0) {
      for (let i = 0; i < data.targets.length; i++) colors.push(SECTION_COLORS[0]);
    } else {
      for (let sgIdx = 0; sgIdx < sectionGroups.length; sgIdx++) {
        const color = SECTION_COLORS[sgIdx % SECTION_COLORS.length];
        for (let i = 0; i < sectionGroups[sgIdx].count; i++) colors.push(color);
      }
    }
    return colors;
  }, [data.targets.length, hasSections, sectionGroups]);
  const todayX = todayXPx;

  const generalGroup = sectionGroups.find((g) => g.id === null);
  const namedGroups = sectionGroups.filter((g) => g.id !== null);

  return (
    <Box ref={wrapperRef} sx={{ width: "100%", overflow: "auto", display: "flex" }}>
      {/* HTML section column — drag-to-reorder */}
      {hasSections && (
        <Box sx={{ width: sectionBarW, flexShrink: 0 }}>
          <Box sx={{ height: MARGIN.top + 1 }} />
          {generalGroup && (
            <SectionBarDiv
              group={generalGroup}
              colorIdx={sectionGroups.indexOf(generalGroup)}
            />
          )}
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleSectionDragEnd}
          >
            <SortableContext
              items={namedSectionIds}
              strategy={verticalListSortingStrategy}
            >
              {namedGroups.map((sg) => (
                <SortableSectionBarDiv
                  key={sg.id!}
                  group={sg}
                  colorIdx={sectionGroups.indexOf(sg)}
                />
              ))}
            </SortableContext>
          </DndContext>
        </Box>
      )}

      {/* Chart column */}
      <Box sx={{ flex: 1, position: "relative" }}>
      <svg
        width={svgWidth}
        height={chartHeight}
        style={{ display: "block" }}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <clipPath id="calendar-clip">
            <rect x={0} y={0} width={innerW} height={innerH} />
          </clipPath>
        </defs>
        <g transform={`translate(${leftMargin},${MARGIN.top + 1})`}>
          {/* Month title row background */}
          <rect
            x={0} y={-MARGIN.top} width={innerW} height={MARGIN.top / 2}
            fill={isDark ? "#1a1a2e" : "#e8eaf0"}
          />
          {/* Moon icons row background */}
          <rect
            x={0} y={-MARGIN.top / 2} width={innerW} height={MARGIN.top / 2}
            fill={isDark ? "#121220" : "#dde0e8"}
          />
          {/* Row backgrounds */}
          {data.targets.map((_, rowIdx) => (
            <rect
              key={`bg-${rowIdx}`}
              x={0}
              y={rowY(rowIdx)}
              width={innerW}
              height={rowH(rowIdx)}
              fill={rowIdx % 2 === 0 ? "transparent" : (isDark ? "#ffffff06" : "#00000004")}
            />
          ))}

          {/* Month grid lines + labels */}
          {monthDates.map((d, i) => {
            const nextX = i + 1 < monthDates.length ? x(monthDates[i + 1]) : x(endDate);
            const midX = (x(d) + nextX) / 2;
            return (
              <g key={d.getTime()}>
                <line
                  x1={x(d)} y1={-MARGIN.top} x2={x(d)} y2={-MARGIN.top / 2}
                  stroke={isDark ? "#555555" : "#cccccc"} strokeWidth={1}
                />
                <line
                  x1={x(d)} y1={0} x2={x(d)} y2={innerH}
                  stroke={isDark ? "#555555" : "#cccccc"} strokeWidth={1}
                />
                <text
                  x={midX} y={-MARGIN.top * 3 / 4}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill={isDark ? "#cccccc" : "#444444"} fontSize={13} fontWeight={600}
                >
                  {d.toLocaleDateString("en", { month: "short", timeZone: "UTC" })}
                </text>
              </g>
            );
          })}
          {/* Outer border — left, top, right of entire calendar */}
          <rect
            x={0} y={-MARGIN.top} width={innerW} height={MARGIN.top + innerH}
            fill="none"
            stroke={isDark ? "#555555" : "#cccccc"} strokeWidth={1}
          />

          {/* Separator line between moon row and data rows */}
          <line x1={0} y1={0} x2={innerW} y2={0}
            stroke={isDark ? "#555555" : "#cccccc"} strokeWidth={1}
          />

          {/* Date range bars — projected to reference year, wraps at Dec/Jan */}
          <g clipPath="url(#calendar-clip)">
            {data.targets.map((target, rowIdx) =>
              target.date_ranges.flatMap((dr: DateRangeOut, rIdx: number) => {
                const rs = toRefDate(dr.start_date);
                const re = toRefDate(dr.end_date);
                const by = rowY(rowIdx);
                const bh = rowH(rowIdx);
                const barThick = 8;
                const barProps = { y: by + (bh - barThick) / 2, height: barThick, rx: 2, fill: rowSectionColor[rowIdx], opacity: 0.8 };

                if (rs <= re) {
                  return [(
                    <rect key={`bar-${rowIdx}-${rIdx}`} x={x(rs)} width={Math.max(2, x(re) - x(rs))} {...barProps} />
                  )];
                }
                return [
                  <rect key={`bar-${rowIdx}-${rIdx}-a`} x={x(rs)} width={Math.max(2, x(endDate) - x(rs))} {...barProps} />,
                  <rect key={`bar-${rowIdx}-${rIdx}-b`} x={0} width={Math.max(2, x(re))} {...barProps} />,
                ];
              }),
            )}
          </g>

          {/* Moon phase markers — projected to reference year */}
          {data.moon_phases.map((mp) => {
            const fmtMoon = (d: Date) => d.toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
            return (
              <g key={mp.month}>
                {mp.new_moon_date && (() => {
                  const nm = toRefDate(mp.new_moon_date);
                  return (
                    <circle cx={x(nm)} cy={-12} r={4}
                      fill={isDark ? "#444444" : "#333333"}
                      stroke={isDark ? "#888888" : "#666666"} strokeWidth={1}
                      style={{ cursor: "pointer" }}
                      onMouseEnter={(e) => {
                        const rect = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
                        setMoonTip({ x: e.clientX - rect.left, y: e.clientY - rect.top - 20, phase: "New Moon", date: fmtMoon(nm) });
                      }}
                      onMouseLeave={() => setMoonTip(null)}
                    />
                  );
                })()}
                {mp.full_moon_date && (() => {
                  const fm = toRefDate(mp.full_moon_date);
                  return (
                    <circle cx={x(fm)} cy={-12} r={4}
                      fill={isDark ? "#dddddd" : "#ffffff"}
                      stroke={isDark ? "#888888" : "#666666"} strokeWidth={1}
                      style={{ cursor: "pointer" }}
                      onMouseEnter={(e) => {
                        const rect = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
                        setMoonTip({ x: e.clientX - rect.left, y: e.clientY - rect.top - 20, phase: "Full Moon", date: fmtMoon(fm) });
                      }}
                      onMouseLeave={() => setMoonTip(null)}
                    />
                  );
                })()}
              </g>
            );
          })}

          {/* Today line — data area only */}
          {todayX >= 0 && todayX <= innerW && (
            <g>
              <line
                x1={todayX} y1={0} x2={todayX} y2={innerH}
                stroke={isDark ? "#ffffff88" : "#00000044"}
                strokeWidth={1.5} strokeDasharray="4,3"
              />
              <text
                x={todayX}
                y={innerH + 14}
                textAnchor="middle"
                fontSize={9}
                fill={isDark ? "#999999" : "#666666"}
              >
                {toRefNow().toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" })}
              </text>
            </g>
          )}

          {/* Row separators */}
          {data.targets.map((_, rowIdx) =>
            rowIdx > 0 ? (
              <line
                key={`sep-${rowIdx}`}
                x1={0} x2={innerW}
                y1={rowY(rowIdx)}
                y2={rowY(rowIdx)}
                stroke={isDark ? "#333333" : "#e0e0e0"} strokeWidth={0.5}
              />
            ) : null,
          )}

          {/* Hover crosshair */}
          {hover && (
            <line
              x1={hover.xPx} y1={0} x2={hover.xPx} y2={innerH}
              stroke={isDark ? "#aaaaaa" : "#666666"}
              strokeWidth={1} strokeDasharray="2,2"
              pointerEvents="none"
            />
          )}
        </g>


        {/* Row labels — clickable to open assignment editor */}
        {data.targets.map((target, rowIdx) => (
          <text
            key={`label-${rowIdx}`}
            x={leftMargin - 8}
            y={MARGIN.top + 1 + rowY(rowIdx) + rowH(rowIdx) / 2}
            textAnchor="end"
            dominantBaseline="middle"
            fontSize={13}
            style={{ cursor: onEditTarget ? "pointer" : undefined }}
            onClick={() => onEditTarget?.(target.dso_id, target.plan_id)}
          >
            <tspan fill={isDark ? "#cccccc" : "#333333"}>{target.primary_designation}</tspan>
            {target.common_name && (
              <tspan fill={isDark ? "#888888" : "#999999"}>{` (${target.common_name})`}</tspan>
            )}
          </text>
        ))}
      </svg>


      {/* Hover tooltip — above the chart */}
      {hover && (
        <Box
          sx={{
            position: "absolute",
            top: -44,
            left: Math.min(hover.xPx + leftMargin + 10, svgWidth - 240),
            bgcolor: "background.paper",
            border: 1,
            borderColor: "divider",
            borderRadius: 1,
            px: 1.5,
            py: 0.75,
            pointerEvents: "none",
            fontSize: 13,
            lineHeight: 1.5,
            minWidth: 160,
            boxShadow: 2,
            zIndex: 1,
          }}
        >
          <Typography variant="caption" fontWeight={600}>
            {hover.dateLabel}
          </Typography>
          {hover.target && hover.rangeLabel && (
            <Box sx={{ color: RIG_ORANGE }}>
              {hover.target}
              <br />
              {hover.rangeLabel}
            </Box>
          )}
        </Box>
      )}

      {/* Moon phase tooltip */}
      {moonTip && (
        <Box
          sx={{
            position: "absolute",
            top: moonTip.y,
            left: moonTip.x + 8,
            bgcolor: "background.paper",
            border: 1,
            borderColor: "divider",
            borderRadius: 1,
            px: 1,
            py: 0.5,
            pointerEvents: "none",
            fontSize: 12,
            boxShadow: 2,
            zIndex: 2,
            whiteSpace: "nowrap",
          }}
        >
          {moonTip.phase} — {moonTip.date}
        </Box>
      )}
      </Box>
    </Box>
  );
}


interface SectionGroup {
  id: number | null;
  name: string;
  startRow: number;
  count: number;
  yStart: number;
  height: number;
}

function SectionBarDiv({
  group,
  colorIdx,
  draggable,
}: {
  group: SectionGroup;
  colorIdx: number;
  draggable?: boolean;
}) {
  const color = SECTION_COLORS[colorIdx % SECTION_COLORS.length];
  return (
    <Box
      sx={{
        height: group.height,
        mb: `${SECTION_GAP}px`,
        mx: "2px",
        borderRadius: "3px",
        bgcolor: `${color}40`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        overflow: "hidden",
        cursor: draggable ? "grab" : undefined,
      }}
    >
      {draggable && (
        <DragIndicatorIcon sx={{ fontSize: 14, color, mb: 0.25 }} />
      )}
      <Box
        sx={{
          writingMode: "vertical-rl",
          transform: "rotate(180deg)",
          fontSize: 10,
          fontWeight: 600,
          color,
          whiteSpace: "nowrap",
          userSelect: "none",
        }}
      >
        {group.name}
      </Box>
    </Box>
  );
}


function SortableSectionBarDiv({
  group,
  colorIdx,
}: {
  group: SectionGroup;
  colorIdx: number;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: group.id! });

  return (
    <Box
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        zIndex: isDragging ? 10 : undefined,
      }}
      {...attributes}
      {...listeners}
    >
      <SectionBarDiv
        group={group}
        colorIdx={colorIdx}
        draggable
      />
    </Box>
  );
}
