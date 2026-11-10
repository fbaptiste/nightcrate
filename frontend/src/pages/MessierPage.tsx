import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Link from "@mui/material/Link";
import { Link as RouterLink, useLocation } from "react-router-dom";
import { fetchLocations } from "@/api/locations";
import { fetchMessier, type MessierParams, type MessierResponse } from "@/api/messier";
import { fetchRigs } from "@/api/rigs";
import type { MessierView } from "@/api/settings";
import GalleryViewer, { type ViewerEntry } from "@/components/gallery/GalleryViewer";
import MessierHeader from "@/components/messier/MessierHeader";
import MessierTile from "@/components/messier/MessierTile";
import MessierToolbar, { type MessierShow } from "@/components/messier/MessierToolbar";
import { viewerImageId } from "@/lib/galleryRendition";
import { SurveyRequestQueue } from "@/lib/surveyRequestQueue";
import { tileMinimums, useTrackWidth } from "@/lib/useTrackWidth";
import { useSettingsStore } from "@/stores/settingsStore";

function imageProjects(slot: MessierResponse["slots"][number]) {
  return slot.projects.filter((project) => project.main_image_id != null);
}

export default function MessierPage() {
  const { pathname } = useLocation();
  const visible = pathname === "/messier";
  const queryClient = useQueryClient();
  const settings = useSettingsStore((state) => state.settings);
  const updateSettings = useSettingsStore((state) => state.update);
  const view: MessierView = settings?.messier_view ?? "medium";
  const imagedStyle = settings?.messier_imaged_style ?? "own";
  const unimagedStyle = settings?.messier_unimaged_style ?? "sky";
  const showProjects = settings?.messier_show_projects ?? false;
  const locationSetting = settings?.messier_location ?? "default";
  const rigSetting = settings?.messier_rig_id ?? null;
  const [show, setShow] = useState<MessierShow>("all");
  const params = useMemo<MessierParams>(() => ({ location: locationSetting, rigId: rigSetting }), [locationSetting, rigSetting]);
  const queryKey = useMemo(() => ["projects", "messier", params] as const, [params]);
  const query = useQuery({ queryKey, queryFn: () => fetchMessier(params), enabled: visible, placeholderData: (previous) => previous });
  const wasVisible = useRef(false);
  useEffect(() => {
    if (visible && !wasVisible.current) void queryClient.invalidateQueries({ queryKey, exact: true });
    wasVisible.current = visible;
  }, [queryClient, queryKey, visible]);

  const locationsQuery = useQuery({ queryKey: ["locations"], queryFn: fetchLocations, enabled: visible });
  const rigsQuery = useQuery({ queryKey: ["rigs", "active", "mine"], queryFn: () => fetchRigs(true, true), enabled: visible });
  const locations = locationsQuery.data ?? [];
  const rigs = useMemo(() => [...(rigsQuery.data ?? [])].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id), [rigsQuery.data]);
  const defaultLocation = locations.find((location) => location.is_default);
  let locationValue: number | "none" = "none";
  if (locationSetting === "default") locationValue = defaultLocation?.id ?? "none";
  if (typeof locationSetting === "number") {
    locationValue = locations.some((location) => location.id === locationSetting)
      ? locationSetting
      : (defaultLocation?.id ?? "none");
  }
  const rigValue = rigSetting != null && rigs.some((rig) => rig.id === rigSetting) ? rigSetting : null;

  const scrollRef = useRef<HTMLDivElement>(null);
  const headerRef = useRef<HTMLDivElement>(null);
  const [headerHeight, setHeaderHeight] = useState(0);
  const surveyRequestQueue = useMemo(() => new SurveyRequestQueue(), []);
  const savedScroll = useRef(0);
  useLayoutEffect(() => {
    if (visible && scrollRef.current) scrollRef.current.scrollTop = savedScroll.current;
  }, [visible]);

  useEffect(() => {
    const header = headerRef.current;
    if (!header) return;
    const observer = new ResizeObserver(() => {
      setHeaderHeight(Math.ceil(header.getBoundingClientRect().height));
    });
    observer.observe(header);
    return () => observer.disconnect();
  }, [query.data?.catalog_status]);

  const gridRef = useRef<HTMLDivElement>(null);
  const trackWidth = useTrackWidth(view, gridRef);
  const [turned, setTurned] = useState<Set<number>>(new Set());
  useEffect(() => { queueMicrotask(() => setTurned(new Set())); }, [show, view]);
  const [shownIndices, setShownIndices] = useState<Map<number, number>>(new Map());
  const previousData = useRef<MessierResponse | undefined>(undefined);
  useEffect(() => {
    if (!query.data || query.data === previousData.current) return;
    const previous = previousData.current;
    setShownIndices((current) => {
      const next = new Map<number, number>();
      for (const slot of query.data.slots) {
        const projects = imageProjects(slot);
        const oldSlot = previous?.slots.find((candidate) => candidate.number === slot.number);
        const oldProjects = oldSlot ? imageProjects(oldSlot) : [];
        const oldProject = oldProjects[current.get(slot.number) ?? 0];
        const retained = oldProject ? projects.findIndex((project) => project.project_id === oldProject.project_id) : -1;
        next.set(slot.number, retained >= 0 ? retained : 0);
      }
      return next;
    });
    previousData.current = query.data;
  }, [query.data]);

  const [viewerKey, setViewerKey] = useState<string | null>(null);
  const expandRefs = useRef(new Map<string, HTMLButtonElement>());
  useEffect(() => { if (!visible) queueMicrotask(() => setViewerKey(null)); }, [visible]);
  const closeViewer = (lastKey: string) => {
    setViewerKey(null);
    requestAnimationFrame(() => {
      const button = expandRefs.current.get(lastKey);
      button?.scrollIntoView({ block: "nearest" });
      button?.focus({ preventScroll: true });
    });
  };

  const data = query.data;
  const filteredSlots = useMemo(() => data?.slots.filter((slot) => show === "all" || (show === "imaged" ? slot.state === "imaged" : slot.state !== "imaged")) ?? [], [data, show]);
  const viewerEntries = useMemo<ViewerEntry[]>(() => data?.slots.flatMap((slot) => {
    if (slot.state !== "imaged") return [];
    const projects = imageProjects(slot);
    const project = projects[shownIndices.get(slot.number) ?? 0];
    if (!project) return [];
    const imageId = viewerImageId(project, view);
    if (imageId == null) return [];
    const title = slot.object?.common_name ? `${slot.object.designation} ${slot.object.common_name}` : (slot.object?.designation ?? `M ${slot.number}`);
    return [{ key: `m${slot.number}`, projectId: project.project_id, imageId, title, subtitle: project.name }];
  }) ?? [], [data, shownIndices, view]);

  const error = query.error instanceof Error ? query.error : null;
  return (
    <Box ref={scrollRef} onScroll={(event) => { if (visible) savedScroll.current = event.currentTarget.scrollTop; }} sx={{ height: "100%", overflow: "auto", scrollPaddingTop: `${headerHeight}px` }}>
      <Box>
        {error && <Box sx={{ p: 3, pb: 0 }}><Alert severity="error">Couldn't load the Messier checklist: {error.message}</Alert></Box>}
        {query.isPending && !data && <Box sx={{ display: "grid", placeItems: "center", py: 8 }}><CircularProgress /></Box>}
        {data?.catalog_status === "not_downloaded" && <Box sx={{ p: 3, py: 6, color: "text.secondary" }}>Download OpenNGC in <Link component={RouterLink} to="/admin">Admin › Catalogs</Link> to show the Messier checklist.</Box>}
        {data?.catalog_status === "ready" && <>
          <MessierHeader
            data={data}
            locations={locations}
            locationValue={locationValue}
            onLocation={(value) => void updateSettings({ messier_location: value })}
            headerRef={headerRef}
            controls={<MessierToolbar
              show={show}
              imagedStyle={imagedStyle}
              unimagedStyle={unimagedStyle}
              rigId={rigValue}
              rigs={rigs}
              rigField={data.rig?.fov_major_deg != null && data.rig.fov_minor_deg != null ? { major: data.rig.fov_major_deg, minor: data.rig.fov_minor_deg } : null}
              rigUnavailable={Boolean(data.rig && data.rig.fov_major_deg == null)}
              showProjects={showProjects}
              view={view}
              onShow={setShow}
              onImagedStyle={(value) => void updateSettings({ messier_imaged_style: value })}
              onUnimagedStyle={(value) => void updateSettings({ messier_unimaged_style: value })}
              onRig={(value) => void updateSettings({ messier_rig_id: value })}
              onShowProjects={(value) => void updateSettings({ messier_show_projects: value })}
              onView={(value) => void updateSettings({ messier_view: value })}
            />}
          />
          <Box sx={{ maxWidth: 1600, px: 3, pt: "20px", pb: 3 }}>
            <Box ref={gridRef} sx={{ display: "grid", gridTemplateColumns: `repeat(auto-fill, minmax(${tileMinimums[view]}px, 1fr))`, columnGap: "16px", rowGap: "16px" }}>
              {filteredSlots.map((slot) => <MessierTile
                key={slot.number}
                slot={slot}
                view={view}
                ws={data.workspace_key}
                trackWidth={trackWidth}
                rig={data.rig}
                imagedStyle={imagedStyle}
                unimagedStyle={unimagedStyle}
                showProjects={showProjects}
                shownProjectIndex={shownIndices.get(slot.number) ?? 0}
                onShownProjectIndex={(index) => setShownIndices((current) => new Map(current).set(slot.number, index))}
                active={visible}
                requestKey={query.dataUpdatedAt}
                scrollRootRef={scrollRef}
                requestQueue={surveyRequestQueue}
                locationName={data.location?.name ?? null}
                turned={turned.has(slot.number)}
                onTurn={(next) => setTurned((current) => { const copy = new Set(current); if (next) copy.add(slot.number); else copy.delete(slot.number); return copy; })}
                onExpand={() => setViewerKey(`m${slot.number}`)}
                expandRefs={expandRefs}
              />)}
            </Box>
          </Box>
          {viewerKey && <GalleryViewer key={`${viewerKey}-${data.workspace_key}`} entries={viewerEntries} startKey={viewerKey} ws={data.workspace_key} onClose={closeViewer} />}
        </>}
      </Box>
    </Box>
  );
}
