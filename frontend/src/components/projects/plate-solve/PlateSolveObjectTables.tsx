import {
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Checkbox from "@mui/material/Checkbox";
import Typography from "@mui/material/Typography";

import type { IdentifiedDso } from "@/api/projectSolve";
import { displayCatalogName } from "@/lib/catalogNames";
import { DSO_TYPE_DISPLAY } from "@/lib/dsoTypeNames";
import {
  sortObjects,
  type ObjectSortKey,
  type SortDirection,
} from "@/lib/plateSolveObjects";

const ROW_HEIGHT = 46;
const MIN_BODY_HEIGHT = ROW_HEIGHT * 5;
const TITLE_HEIGHT = 36;
const HEADER_HEIGHT = 34;
const MIN_TABLE_HEIGHT = TITLE_HEIGHT + HEADER_HEIGHT + MIN_BODY_HEIGHT + 2;

export interface PlateSolveTablesHandle {
  scrollToObject: (id: number) => void;
  focusCheckbox: (id: number, mainTable: boolean) => void;
}

interface Props {
  otherObjects: IdentifiedDso[];
  totalOtherCount: number;
  mainObjects: IdentifiedDso[];
  selectedId: number | null;
  pendingIds: ReadonlySet<number>;
  onSelect: (id: number) => void;
  onToggleMain: (object: IdentifiedDso, isMain: boolean) => Promise<boolean>;
}

interface Column {
  key: ObjectSortKey | null;
  label: string;
  width: string;
  align?: "left" | "right" | "center";
}

interface VirtualRowsProps {
  objects: IdentifiedDso[];
  columns: string;
  selectedId: number | null;
  pendingIds: ReadonlySet<number>;
  onSelect: (id: number) => void;
  onToggleMain: (object: IdentifiedDso, isMain: boolean) => Promise<boolean>;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  onScrollTop: (top: number) => void;
  scrollTop: number;
  mainTable: boolean;
}

function formatAxis(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function objectSize(object: IdentifiedDso): string {
  const major = object.maj_axis_arcmin;
  const minor = object.min_axis_arcmin;
  if (major == null) return "—";
  if (minor == null || Math.abs(major - minor) < 0.05) return `${formatAxis(major)}′`;
  return `${formatAxis(major)}′ × ${formatAxis(minor)}′`;
}

function secondaryNames(object: IdentifiedDso, mainTable: boolean): string {
  const values = mainTable
    ? [object.common_name]
    : [object.common_name, ...object.other_names];
  const primary = object.primary_designation.toLocaleLowerCase();
  return Array.from(
    new Set(values.filter((value): value is string => Boolean(value) && value!.toLocaleLowerCase() !== primary)),
  ).join(", ");
}

const VirtualRows = memo(function VirtualRows({
  objects,
  columns,
  selectedId,
  pendingIds,
  onSelect,
  onToggleMain,
  scrollRef,
  onScrollTop,
  scrollTop,
  mainTable,
}: VirtualRowsProps) {
  const [bodyHeight, setBodyHeight] = useState(MIN_BODY_HEIGHT);
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const measure = () => {
      const nextHeight = container.clientHeight;
      if (nextHeight > 0) {
        setBodyHeight((current) => (current === nextHeight ? current : nextHeight));
      }
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    return () => observer.disconnect();
  }, [scrollRef]);
  const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 4);
  const end = Math.min(objects.length, start + Math.ceil(bodyHeight / ROW_HEIGHT) + 8);
  const visible = objects.slice(start, end);
  return (
    <Box
      ref={scrollRef}
      role="rowgroup"
      onScroll={(event) => onScrollTop(event.currentTarget.scrollTop)}
      sx={{ flex: "1 1 auto", minHeight: MIN_BODY_HEIGHT, overflowY: "auto", position: "relative" }}
    >
      <Box sx={{ height: objects.length * ROW_HEIGHT, position: "relative" }}>
        {visible.map((object, offset) => {
          const title = object.primary_designation;
          const secondary = secondaryNames(object, mainTable);
          const selected = selectedId === object.dso_id;
          const disabled = pendingIds.has(object.dso_id) || (!object.active && !object.is_main);
          return (
            <Box
              role="row"
              aria-selected={selected}
              tabIndex={0}
              key={object.dso_id}
              data-object-id={object.dso_id}
              onClick={() => onSelect(object.dso_id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(object.dso_id);
                }
              }}
              sx={{
                position: "absolute",
                top: (start + offset) * ROW_HEIGHT,
                left: 0,
                right: 0,
                height: ROW_HEIGHT,
                display: "grid",
                gridTemplateColumns: columns,
                alignItems: "center",
                borderTop: 1,
                borderColor: "divider",
                borderLeft: "3px solid",
                borderLeftColor: selected ? "#ffd400" : object.is_main ? "#64a8f0" : "transparent",
                bgcolor: selected ? "rgba(255,212,0,0.12)" : "transparent",
                cursor: "pointer",
                "&:hover": { bgcolor: selected ? "rgba(255,212,0,0.12)" : "action.hover" },
                "&:focus-visible": { outline: "2px solid", outlineColor: "primary.main", outlineOffset: -2 },
              }}
            >
              <Box role="cell" sx={{ minWidth: 0, px: 1 }}>
                <Typography noWrap sx={{ fontSize: 12.5, fontWeight: 600 }}>{title}</Typography>
                {secondary && <Typography noWrap color="text.secondary" sx={{ fontSize: 11 }}>{secondary}</Typography>}
              </Box>
              <Typography role="cell" noWrap sx={{ px: 1, fontSize: 12 }}>
                {DSO_TYPE_DISPLAY[object.obj_type] ?? object.obj_type}
              </Typography>
              {!mainTable && (
                <Typography role="cell" noWrap color="text.secondary" sx={{ px: 1, fontSize: 11.5 }}>
                  {object.catalogs.map(displayCatalogName).join(", ") || "—"}
                </Typography>
              )}
              {!mainTable && (
                <Typography role="cell" noWrap sx={{ px: 1, textAlign: "right", fontSize: 12 }}>
                  {objectSize(object)}
                </Typography>
              )}
              <Box
                role="cell"
                sx={{ display: "grid", placeItems: "center" }}
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
              >
                <Checkbox
                  size="small"
                  data-main-id={object.dso_id}
                  checked={object.is_main}
                  disabled={disabled}
                  onChange={async (event) => {
                    const changed = await onToggleMain(object, event.target.checked);
                    if (!changed) event.target.focus();
                  }}
                  inputProps={{ "aria-label": `Main target: ${title}` }}
                  sx={{ color: "#64a8f0", "&.Mui-checked": { color: "#64a8f0" } }}
                />
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
});

interface ObjectTableProps {
  title: string;
  countText: string;
  objects: IdentifiedDso[];
  columns: Column[];
  defaultSort: ObjectSortKey;
  defaultDirection: SortDirection;
  selectedId: number | null;
  pendingIds: ReadonlySet<number>;
  onSelect: (id: number) => void;
  onToggleMain: (object: IdentifiedDso, isMain: boolean) => Promise<boolean>;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  titleRef: React.RefObject<HTMLHeadingElement | null>;
  mainTable: boolean;
  onOrderChange: (objects: IdentifiedDso[]) => void;
}

function ObjectTable({
  title,
  countText,
  objects,
  columns,
  defaultSort,
  defaultDirection,
  selectedId,
  pendingIds,
  onSelect,
  onToggleMain,
  scrollRef,
  titleRef,
  mainTable,
  onOrderChange,
}: ObjectTableProps) {
  const [sortKey, setSortKey] = useState<ObjectSortKey>(defaultSort);
  const [direction, setDirection] = useState<SortDirection>(defaultDirection);
  const [scrollTop, setScrollTop] = useState(0);
  const sorted = useMemo(() => sortObjects(objects, sortKey, direction), [objects, sortKey, direction]);
  useEffect(() => onOrderChange(sorted), [onOrderChange, sorted]);
  const gridColumns = columns.map((column) => column.width).join(" ");
  const chooseSort = (key: ObjectSortKey) => {
    if (sortKey === key) setDirection((value) => (value === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setDirection(key === "size" ? "desc" : "asc");
    }
  };
  return (
    <Box role="table" aria-label={title} sx={{ height: "100%", minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column", border: 1, borderColor: "divider", borderRadius: "8px", overflow: "hidden", bgcolor: "background.paper" }}>
      <Box sx={{ px: 1.25, height: TITLE_HEIGHT, flexShrink: 0, display: "flex", alignItems: "center", gap: 1 }}>
        <Typography ref={titleRef} component="h2" tabIndex={-1} sx={{ color: mainTable ? "#4fb0ff" : "text.primary", fontSize: 13, fontWeight: 600 }}>{title}</Typography>
        <Typography color="text.secondary" sx={{ fontSize: 12 }}>{countText}</Typography>
      </Box>
      <Box role="row" sx={{ height: HEADER_HEIGHT, flexShrink: 0, display: "grid", gridTemplateColumns: gridColumns, alignItems: "stretch", borderTop: 1, borderColor: "divider" }}>
        {columns.map((column) => {
          if (column.key == null) {
            return (
              <Box
                role="columnheader"
                key={column.label}
                sx={{ display: "flex", alignItems: "center", justifyContent: "center", px: 1, color: "text.secondary", fontSize: 11.5, fontWeight: 600 }}
              >
                {column.label}
              </Box>
            );
          }
          const key = column.key;
          const active = sortKey === key;
          const ariaSort = active ? (direction === "asc" ? "ascending" : "descending") : "none";
          return (
            <Box
              role="columnheader"
              aria-sort={ariaSort}
              key={column.label}
            >
              <ButtonBase
                onClick={() => chooseSort(key)}
                sx={{ width: "100%", height: "100%", justifyContent: column.align === "right" ? "flex-end" : column.align === "center" ? "center" : "flex-start", px: 1, color: "text.secondary", fontSize: 11.5, fontWeight: 600, whiteSpace: "nowrap" }}
              >
                {column.label}{active ? (direction === "asc" ? " ▲" : " ▼") : ""}
              </ButtonBase>
            </Box>
          );
        })}
      </Box>
      <VirtualRows
        objects={sorted}
        columns={gridColumns}
        selectedId={selectedId}
        pendingIds={pendingIds}
        onSelect={onSelect}
        onToggleMain={onToggleMain}
        scrollRef={scrollRef}
        onScrollTop={setScrollTop}
        scrollTop={scrollTop}
        mainTable={mainTable}
      />
    </Box>
  );
}

const PlateSolveObjectTables = forwardRef<PlateSolveTablesHandle, Props>(function PlateSolveObjectTables(
  { otherObjects, totalOtherCount, mainObjects, selectedId, pendingIds, onSelect, onToggleMain },
  ref,
) {
  const otherScrollRef = useRef<HTMLDivElement | null>(null);
  const mainScrollRef = useRef<HTMLDivElement | null>(null);
  const otherTitleRef = useRef<HTMLHeadingElement | null>(null);
  const mainTitleRef = useRef<HTMLHeadingElement | null>(null);
  const otherOrderRef = useRef<IdentifiedDso[]>(otherObjects);
  const mainOrderRef = useRef<IdentifiedDso[]>(mainObjects);
  const setOtherOrder = useCallback((objects: IdentifiedDso[]) => {
    otherOrderRef.current = objects;
  }, []);
  const setMainOrder = useCallback((objects: IdentifiedDso[]) => {
    mainOrderRef.current = objects;
  }, []);
  const find = useCallback(
    (id: number, targetMain?: boolean) => {
      const main = targetMain ?? mainObjects.some((object) => object.dso_id === id);
      const list = main ? mainOrderRef.current : otherOrderRef.current;
      return { container: main ? mainScrollRef.current : otherScrollRef.current, index: list.findIndex((object) => object.dso_id === id) };
    },
    [mainObjects],
  );
  const scrollToObject = useCallback((id: number) => {
    const { container, index } = find(id);
    if (!container || index < 0) return;
    const top = index * ROW_HEIGHT;
    if (top < container.scrollTop) container.scrollTop = top;
    else if (top + ROW_HEIGHT > container.scrollTop + container.clientHeight) {
      container.scrollTop = top + ROW_HEIGHT - container.clientHeight;
    }
  }, [find]);
  useImperativeHandle(ref, () => ({
    scrollToObject,
    focusCheckbox: (id: number, mainTable: boolean) => {
      const { container, index } = find(id, mainTable);
      if (container && index >= 0) {
        const top = index * ROW_HEIGHT;
        if (top < container.scrollTop) container.scrollTop = top;
        else if (top + ROW_HEIGHT > container.scrollTop + container.clientHeight) {
          container.scrollTop = top + ROW_HEIGHT - container.clientHeight;
        }
      }
      requestAnimationFrame(() => requestAnimationFrame(() => {
        const target = find(id, mainTable).container?.querySelector<HTMLInputElement>(
          `[data-main-id="${id}"] input`,
        );
        if (target) target.focus();
        else (mainTable ? mainTitleRef : otherTitleRef).current?.focus();
      }));
    },
  }), [find, scrollToObject]);

  return (
    <Box sx={{ flex: "1 1 0", minHeight: MIN_TABLE_HEIGHT, display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(290px, 1fr)", alignItems: "stretch", gap: 1.5, minWidth: 0 }}>
      <ObjectTable
        title="Other objects in the image"
        countText={otherObjects.length === totalOtherCount ? String(totalOtherCount) : `${otherObjects.length} of ${totalOtherCount}`}
        objects={otherObjects}
        columns={[
          { key: "name", label: "Object", width: "minmax(150px, 1.3fr)" },
          { key: "type", label: "Type", width: "minmax(120px, 1fr)" },
          { key: "catalogs", label: "Catalogs", width: "minmax(100px, 0.85fr)" },
          { key: "size", label: "Size", width: "minmax(105px, 0.75fr)", align: "right" },
          { key: null, label: "Main", width: "58px", align: "center" },
        ]}
        defaultSort="size"
        defaultDirection="desc"
        selectedId={selectedId}
        pendingIds={pendingIds}
        onSelect={onSelect}
        onToggleMain={onToggleMain}
        scrollRef={otherScrollRef}
        titleRef={otherTitleRef}
        mainTable={false}
        onOrderChange={setOtherOrder}
      />
      <ObjectTable
        title="Main targets"
        countText={String(mainObjects.length)}
        objects={mainObjects}
        columns={[
          { key: "name", label: "Object", width: "minmax(130px, 1.25fr)" },
          { key: "type", label: "Type", width: "minmax(105px, 0.9fr)" },
          { key: null, label: "Main", width: "58px", align: "center" },
        ]}
        defaultSort="name"
        defaultDirection="asc"
        selectedId={selectedId}
        pendingIds={pendingIds}
        onSelect={onSelect}
        onToggleMain={onToggleMain}
        scrollRef={mainScrollRef}
        titleRef={mainTitleRef}
        mainTable
        onOrderChange={setMainOrder}
      />
    </Box>
  );
});

export default PlateSolveObjectTables;
