import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { Link as RouterLink, useLocation } from "react-router-dom";
import { fetchGallery, type GalleryParams, type GalleryResponse } from "@/api/gallery";
import type { GalleryView } from "@/api/settings";
import GalleryFilters from "@/components/gallery/GalleryFilters";
import GalleryGrid from "@/components/gallery/GalleryGrid";
import GalleryList from "@/components/gallery/GalleryList";
import GalleryResultsBar from "@/components/gallery/GalleryResultsBar";
import GalleryViewer from "@/components/gallery/GalleryViewer";
import { cropSizeForView } from "@/lib/galleryRendition";
import { useDebounce } from "@/lib/useDebounce";
import { useGalleryStore } from "@/stores/galleryStore";
import { useSettingsStore } from "@/stores/settingsStore";

interface GalleryBodyProps {
  data?: GalleryResponse;
  pending: boolean;
  error: Error | null;
  view: GalleryView;
  resetKey: string;
  onClear: () => void;
  onExpand: (projectId: number) => void;
  expandRefs: React.RefObject<Map<number, HTMLButtonElement>>;
}

function GalleryBody({
  data,
  pending,
  error,
  view,
  resetKey,
  onClear,
  onExpand,
  expandRefs,
}: GalleryBodyProps) {
  const errorAlert = error ? (
    <Alert severity="error" sx={{ mb: 2 }}>
      Couldn't load the gallery: {error.message}
    </Alert>
  ) : null;

  if (pending && !data) {
    return (
      <>
        {errorAlert}
        <Box sx={{ display: "grid", placeItems: "center", py: 8 }}>
          <CircularProgress />
        </Box>
      </>
    );
  }
  if (data?.library_total === 0) {
    return (
      <>
        {errorAlert}
        <Box sx={{ py: 6, color: "text.secondary" }}>
          No projects yet. <Link component={RouterLink} to="/projects">Create a project</Link>{" "}
          to see it here.
        </Box>
      </>
    );
  }
  if (data && data.items.length === 0) {
    return (
      <>
        {errorAlert}
        <Box sx={{ py: 6, color: "text.secondary" }}>
          No projects match these filters. <Button onClick={onClear}>Clear filters</Button>
        </Box>
      </>
    );
  }
  if (!data) return errorAlert;

  const gallery = view === "list" ? (
    <GalleryList
      items={data.items}
      ws={data.workspace_key}
      onExpand={onExpand}
      expandRefs={expandRefs}
    />
  ) : (
    <GalleryGrid
      items={data.items}
      view={view}
      ws={data.workspace_key}
      resetKey={resetKey}
      onExpand={onExpand}
      expandRefs={expandRefs}
    />
  );
  return (
    <>
      {errorAlert}
      {gallery}
    </>
  );
}

export default function GalleryPage() {
  const { pathname } = useLocation();
  const visible = pathname === "/gallery";
  const queryClient = useQueryClient();
  const state = useGalleryStore();
  const debouncedSearch = useDebounce(state.search, 300);
  const invalidRange = Boolean(
    state.dateFrom && state.dateTo && state.dateFrom > state.dateTo,
  );
  const params = useMemo<GalleryParams>(
    () => ({
      q: debouncedSearch.trim() || undefined,
      search_images: state.searchImages,
      catalog: state.catalogs,
      type_group: state.typeGroups,
      constellation: state.constellations,
      status: state.statuses,
      rig: state.rigs.map(Number),
      imaged_from: state.dateFrom || undefined,
      imaged_to: state.dateTo || undefined,
      include_undated: state.includeUndated,
      include_retired: state.includeRetired,
      sort: state.sort,
      desc: state.desc,
    }),
    [
      debouncedSearch,
      state.searchImages,
      state.catalogs,
      state.typeGroups,
      state.constellations,
      state.statuses,
      state.rigs,
      state.dateFrom,
      state.dateTo,
      state.includeUndated,
      state.includeRetired,
      state.sort,
      state.desc,
    ],
  );
  const queryKey = useMemo(() => ["projects", "gallery", params] as const, [params]);
  const query = useQuery({
    queryKey,
    queryFn: () => fetchGallery(params),
    enabled: visible && !invalidRange,
    placeholderData: (previous) => previous,
  });
  const wasVisible = useRef(false);
  useEffect(() => {
    if (visible && !wasVisible.current) {
      void queryClient.invalidateQueries({ queryKey, exact: true });
    }
    wasVisible.current = visible;
  }, [visible, queryClient, queryKey]);

  const scrollRef = useRef<HTMLDivElement>(null);
  const savedScroll = useRef(0);
  useLayoutEffect(() => {
    if (visible && scrollRef.current) {
      scrollRef.current.scrollTop = savedScroll.current;
    }
  }, [visible]);

  const settings = useSettingsStore((store) => store.settings);
  const updateSettings = useSettingsStore((store) => store.update);
  const view: GalleryView = settings?.gallery_view ?? "medium";
  const [viewerId, setViewerId] = useState<number | null>(null);
  const expandRefs = useRef(new Map<number, HTMLButtonElement>());
  useEffect(() => {
    if (!visible) queueMicrotask(() => setViewerId(null));
  }, [visible]);

  const closeViewer = (lastId: number) => {
    setViewerId(null);
    requestAnimationFrame(() => {
      const button = expandRefs.current.get(lastId);
      button?.scrollIntoView({ block: "nearest" });
      button?.focus({ preventScroll: true });
    });
  };
  const hasFilters = Boolean(
    state.search ||
      state.searchImages ||
      state.catalogs.length ||
      state.typeGroups.length ||
      state.constellations.length ||
      state.statuses.length ||
      state.rigs.length ||
      state.dateFrom ||
      state.dateTo ||
      state.includeUndated ||
      state.includeRetired,
  );
  const data = query.data;
  const resetKey = JSON.stringify(params);
  const queryError = query.error instanceof Error ? query.error : null;

  return (
    <Box
      ref={scrollRef}
      onScroll={(event) => {
        if (visible) savedScroll.current = event.currentTarget.scrollTop;
      }}
      sx={{ height: "100%", overflow: "auto" }}
    >
      <Box sx={{ maxWidth: 1600, p: 3 }}>
        <Typography
          variant="h4"
          component="h1"
          sx={{ mb: "20px", fontSize: 24, fontWeight: 600 }}
        >
          Gallery
        </Typography>
        <GalleryFilters
          values={state}
          facets={data?.facets}
          invalidRange={invalidRange}
          onChange={state.set}
          onClear={state.reset}
          hasFilters={hasFilters}
        />
        <GalleryResultsBar
          count={data?.items.length ?? 0}
          sort={state.sort}
          desc={state.desc}
          view={view}
          onSort={(sort) => state.set({ sort })}
          onDirection={() => state.set({ desc: !state.desc })}
          onView={(next) => void updateSettings({ gallery_view: next })}
        />
        <GalleryBody
          data={data}
          pending={query.isPending}
          error={queryError}
          view={view}
          resetKey={resetKey}
          onClear={state.reset}
          onExpand={setViewerId}
          expandRefs={expandRefs}
        />
        {data && viewerId != null && (
          <GalleryViewer
            key={`${viewerId}-${data.workspace_key}`}
            items={data.items}
            startId={viewerId}
            ws={data.workspace_key}
            cropSize={cropSizeForView(view)}
            onClose={closeViewer}
          />
        )}
      </Box>
    </Box>
  );
}
