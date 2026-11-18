import { useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";

import type { IdentifiedDso, ProjectSolve } from "@/api/projectSolve";
import { projectSolveImageUrl } from "@/api/projectSolve";
import { displayCatalogName } from "@/lib/catalogNames";
import { DSO_TYPE_DISPLAY } from "@/lib/dsoTypeNames";
import { facetCounts, filterObjects } from "@/lib/plateSolveObjects";
import PlateSolveObjectTables, {
  type PlateSolveTablesHandle,
} from "./PlateSolveObjectTables";
import PlateSolveSidePanel from "./PlateSolveSidePanel";
import PlateSolveViewer, { type PlateSolveViewerHandle } from "./PlateSolveViewer";
import { usePlateSolveFilters } from "./usePlateSolveFilters";

interface Props {
  projectId: number;
  solve: ProjectSolve;
  pendingIds: ReadonlySet<number>;
  onToggleMain: (object: IdentifiedDso, isMain: boolean) => Promise<boolean>;
}

export default function SolvedPlateSolveWorkspace({
  projectId,
  solve,
  pendingIds,
  onToggleMain,
}: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const tablesRef = useRef<PlateSolveTablesHandle | null>(null);
  const viewerRef = useRef<PlateSolveViewerHandle | null>(null);
  const {
    filters,
    toggleCatalog,
    toggleType,
    setMinimumSize,
    clear,
    activeCount,
  } = usePlateSolveFilters();

  const mainIds = useMemo(
    () => new Set(solve.objects.filter((object) => object.is_main).map((object) => object.dso_id)),
    [solve.objects],
  );
  const mainObjects = useMemo(
    () => solve.objects.filter((object) => object.is_main),
    [solve.objects],
  );
  const allOtherObjects = useMemo(
    () => solve.objects.filter((object) => !object.is_main),
    [solve.objects],
  );
  const filteredObjects = useMemo(
    () => filterObjects(solve.objects, filters, mainIds),
    [filters, mainIds, solve.objects],
  );
  const otherObjects = useMemo(
    () => filteredObjects.filter((object) => !object.is_main),
    [filteredObjects],
  );
  const facets = useMemo(
    () => facetCounts(solve.objects, filters, mainIds),
    [filters, mainIds, solve.objects],
  );
  const catalogs = useMemo(
    () =>
      Array.from(new Set(solve.objects.flatMap((object) => object.catalogs))).sort((a, b) =>
        displayCatalogName(a).localeCompare(displayCatalogName(b), undefined, { numeric: true }),
      ),
    [solve.objects],
  );
  const types = useMemo(
    () =>
      Array.from(new Set(solve.objects.map((object) => object.obj_type))).sort((a, b) =>
        (DSO_TYPE_DISPLAY[a] ?? a).localeCompare(DSO_TYPE_DISPLAY[b] ?? b),
      ),
    [solve.objects],
  );
  const maxSizeArcmin = useMemo(
    () => Math.max(0, ...allOtherObjects.map((object) => object.maj_axis_arcmin ?? 0)),
    [allOtherObjects],
  );
  const overlayDsos = useMemo(
    () =>
      filteredObjects.map((object) => ({
        id: object.dso_id,
        pixel_x: object.pixel_x,
        pixel_y: object.pixel_y,
        ellipse_semi_major_px: object.ellipse_semi_major_px,
        ellipse_semi_minor_px: object.ellipse_semi_minor_px,
        ellipse_angle_deg: object.ellipse_angle_deg,
        common_name: object.common_name,
        primary_designation: object.primary_designation,
      })),
    [filteredObjects],
  );

  const visibleSelectedId =
    selectedId != null && filteredObjects.some((object) => object.dso_id === selectedId)
      ? selectedId
      : null;

  const toggleAndFocus = async (object: IdentifiedDso, isMain: boolean) => {
    const change = onToggleMain(object, isMain);
    requestAnimationFrame(() => tablesRef.current?.focusCheckbox(object.dso_id, isMain));
    const changed = await change;
    tablesRef.current?.focusCheckbox(object.dso_id, changed ? isMain : !isMain);
    return changed;
  };

  return (
    <Box sx={{ flex: 1, minHeight: 560, display: "flex", gap: 1.5, minWidth: 0 }}>
      <PlateSolveSidePanel
        collapsed={collapsed}
        onCollapsedChange={setCollapsed}
        activeCount={activeCount}
        filters={filters}
        facets={facets}
        catalogs={catalogs}
        types={types}
        maxSizeArcmin={maxSizeArcmin}
        onToggleCatalog={toggleCatalog}
        onToggleType={toggleType}
        onMinimumSizeChange={setMinimumSize}
        onClear={clear}
      />
      <Box sx={{ flex: 1, minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column", gap: 1 }}>
        <PlateSolveViewer
          ref={viewerRef}
          imageHref={projectSolveImageUrl(projectId, "full", solve.id)}
          imgW={solve.image_width}
          imgH={solve.image_height}
          dsos={overlayDsos}
          mainIds={mainIds}
          selectedId={visibleSelectedId}
          onSelect={(id) => {
            setSelectedId(id);
            tablesRef.current?.scrollToObject(id);
          }}
          onDoubleSelect={(id) => {
            const object = solve.objects.find((item) => item.dso_id === id);
            if (object && !pendingIds.has(id) && (object.active || object.is_main)) {
              void toggleAndFocus(object, !object.is_main);
            }
          }}
        />
        <PlateSolveObjectTables
          ref={tablesRef}
          otherObjects={otherObjects}
          totalOtherCount={allOtherObjects.length}
          mainObjects={mainObjects}
          selectedId={visibleSelectedId}
          pendingIds={pendingIds}
          onSelect={(id) => {
            setSelectedId(id);
            viewerRef.current?.revealObject(id);
          }}
          onToggleMain={toggleAndFocus}
        />
      </Box>
    </Box>
  );
}
