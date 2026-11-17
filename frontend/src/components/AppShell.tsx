import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import KeyboardDoubleArrowLeftIcon from "@mui/icons-material/KeyboardDoubleArrowLeft";
import KeyboardDoubleArrowRightIcon from "@mui/icons-material/KeyboardDoubleArrowRight";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import DesktopWindowsIcon from "@mui/icons-material/DesktopWindows";
import HomeIcon from "@mui/icons-material/Home";
import ImageSearchIcon from "@mui/icons-material/ImageSearch";
import LightModeIcon from "@mui/icons-material/LightMode";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import BuildIcon from "@mui/icons-material/Build";
import CalculateOutlinedIcon from "@mui/icons-material/CalculateOutlined";
import CodeIcon from "@mui/icons-material/Code";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import PlaceIcon from "@mui/icons-material/Place";
import PrecisionManufacturingIcon from "@mui/icons-material/PrecisionManufacturing";
import SettingsIcon from "@mui/icons-material/Settings";
import StarsIcon from "@mui/icons-material/Stars";
import NightsStayIcon from "@mui/icons-material/NightsStay";
import WbSunnyIcon from "@mui/icons-material/WbSunny";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import TimelineIcon from "@mui/icons-material/Timeline";
import CollectionsIcon from "@mui/icons-material/Collections";
import ViewQuiltIcon from "@mui/icons-material/ViewQuilt";
import ChecklistIcon from "@mui/icons-material/Checklist";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { ImageAnalyzerPage } from "@/pages/ImageAnalyzerPage";
import PlannerPage from "@/pages/PlannerPage";
import Phd2AnalyzerPage from "@/pages/Phd2AnalyzerPage";
import DsoCatalogPage from "@/pages/DsoCatalogPage";
import WeatherPage from "@/pages/WeatherPage";
import GalleryPage from "@/pages/GalleryPage";
import MessierPage from "@/pages/MessierPage";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { fetchHealth } from "@/api/files";
import { fetchAdminStatus } from "@/api/admin";
import { setActivity } from "@/api/client";
import { useSettingsStore } from "@/stores/settingsStore";
import { resetZoom, resetZoomShortcut, useDesktopZoom } from "@/lib/desktopZoom";
import { createDragClickGuard } from "@/lib/dragClickGuard";
import { ActivityConsole } from "@/components/ActivityConsole";
import type { Theme } from "@/api/settings";
import { EasterEggWand } from "@/components/EasterEggWand";
import { WandToast } from "@/components/WandToast";
import { WandToastContext } from "@/components/WandToastContext";
import { ASTRO_JOKES } from "@/lib/astroJokes";
import { NoticesPill } from "@/components/notices/NoticesPill";
import { NoticesPanel } from "@/components/notices/NoticesPanel";
import { useNotices } from "@/components/notices/useNotices";
import { UpdateQuestionDialog } from "@/components/notices/UpdateQuestionDialog";
import { useInstallFlow } from "@/components/notices/InstallUpdateDialog";
import { AppToast } from "@/components/notices/AppToast";
import { markVersionSeen, setCheckAutomatically } from "@/api/updates";
import { onDownloadSaved } from "@/lib/desktopShell";
import { PageErrorBoundary } from "@/components/common/PageError";

const DRAWER_WIDTH_OPEN = 220;
const DRAWER_WIDTH_CLOSED = 52;

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
}

/** Home is pinned at the top and is NOT part of the drag-reorderable set. */
const HOME_ITEM: NavItem = { to: "/", label: "Home", icon: <HomeIcon /> };

/** Reorderable nav items in their default display order. The user's
 *  saved order (``settings.nav_order``) overrides this; unknown routes
 *  are filtered and newly-added routes appear at the end. */
const REORDERABLE_ITEMS: NavItem[] = [
  { to: "/tonight", label: "Tonight", icon: <NightsStayIcon /> },
  { to: "/planner", label: "Planner", icon: <StarsIcon /> },
  { to: "/weather", label: "Weather", icon: <WbSunnyIcon /> },
  { to: "/projects", label: "Projects", icon: <CollectionsIcon /> },
  { to: "/gallery", label: "Gallery", icon: <ViewQuiltIcon /> },
  { to: "/messier", label: "Messier", icon: <ChecklistIcon /> },
  { to: "/image-analyzer", label: "Image Analyzer", icon: <ImageSearchIcon /> },
  { to: "/phd2-analyzer", label: "PHD2 Analyzer", icon: <ShowChartIcon /> },
  { to: "/catalog/dso", label: "DSO Catalog", icon: <AutoAwesomeIcon /> },
  { to: "/calculators", label: "Calculators", icon: <CalculateOutlinedIcon /> },
  { to: "/locations", label: "Locations", icon: <PlaceIcon /> },
  { to: "/rigs", label: "Rigs", icon: <PrecisionManufacturingIcon /> },
  { to: "/equipment", label: "Equipment", icon: <BuildIcon /> },
  { to: "/settings", label: "Settings", icon: <SettingsIcon /> },
  { to: "/admin", label: "Admin", icon: <AdminPanelSettingsIcon /> },
  { to: "/api-docs", label: "API Docs", icon: <CodeIcon /> },
];

const ALL_NAV_ITEMS: NavItem[] = [HOME_ITEM, ...REORDERABLE_ITEMS];

/** Drop unknown routes, then insert missing routes beside their nearest
 * default predecessor without disturbing the relative order the user saved.
 *
 * | saved order                         | relevant normalized result       |
 * | /projects, /gallery, /image-analyzer | unchanged                       |
 * | /projects, /image-analyzer (no gallery) | /projects, /gallery, /image-analyzer |
 * | /api-docs (no preceding routes)     | /tonight first                   |
 */
function normalizeNavOrder(raw: readonly unknown[] | undefined): string[] {
  const known = new Set<string>(REORDERABLE_ITEMS.map((i) => i.to));
  const seen = new Set<string>();
  const out: string[] = [];
  if (Array.isArray(raw)) {
    for (const entry of raw) {
      if (typeof entry === "string" && known.has(entry) && !seen.has(entry)) {
        out.push(entry);
        seen.add(entry);
      }
    }
  }
  for (let index = 0; index < REORDERABLE_ITEMS.length; index += 1) {
    const route = REORDERABLE_ITEMS[index].to;
    if (seen.has(route)) continue;

    let predecessor: string | null = null;
    for (let previous = index - 1; previous >= 0; previous -= 1) {
      const candidate = REORDERABLE_ITEMS[previous].to;
      if (seen.has(candidate)) {
        predecessor = candidate;
        break;
      }
    }
    if (predecessor == null) {
      out.unshift(route);
    } else {
      out.splice(out.indexOf(predecessor) + 1, 0, route);
    }
    seen.add(route);
  }
  return out;
}

const THEME_CYCLE: Theme[] = ["light", "dark", "browser"];
const THEME_ICONS: Record<Theme, React.ReactNode> = {
  light: <LightModeIcon sx={{ fontSize: 16 }} />,
  dark: <DarkModeIcon sx={{ fontSize: 16 }} />,
  browser: <DesktopWindowsIcon sx={{ fontSize: 16 }} />,
};
const THEME_LABELS: Record<Theme, string> = {
  light: "Light",
  dark: "Dark",
  browser: "System",
};

function resolvePageLabel(pathname: string): string | null {
  const match = ALL_NAV_ITEMS.find((n) =>
    n.to === "/" ? pathname === "/" : pathname === n.to || pathname.startsWith(n.to + "/"),
  );
  return match?.label ?? null;
}

export function AppShell() {
  // Set a page-level activity label synchronously on route change so the
  // route component's initial queries get tagged. Child pages (like Image
  // Viewer) can still override with finer-grained action labels; the next
  // route change resets the default.
  const { pathname } = useLocation();
  const lastPathname = useRef<string | null>(null);
  // Activity must be set before the newly rendered page starts its first query.
  // eslint-disable-next-line react-hooks/refs
  if (lastPathname.current !== pathname) {
    // eslint-disable-next-line react-hooks/refs
    lastPathname.current = pathname;
    setActivity(resolvePageLabel(pathname));
  }

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    staleTime: Infinity,
  });
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ["admin-status"],
    queryFn: fetchAdminStatus,
    staleTime: 60_000,
  });
  const activeDbName = statusQuery.data?.active_db?.name;
  const installFlow = useInstallFlow();
  const notices = useNotices(installFlow.start);
  const [noticeAnchor, setNoticeAnchor] = useState<HTMLElement | null>(null);
  const [questionDismissed, setQuestionDismissed] = useState(false);
  const [downloadToast, setDownloadToast] = useState<string | null>(null);
  const [updatedToastVersion, setUpdatedToastVersion] = useState<string | null>(null);
  const updateSeen = useRef<string | null>(null);
  const { settings, update } = useSettingsStore();
  const zoom = useDesktopZoom();
  const currentTheme: Theme = settings?.theme ?? "browser";

  const cycleTheme = () => {
    const idx = THEME_CYCLE.indexOf(currentTheme);
    const next = THEME_CYCLE[(idx + 1) % THEME_CYCLE.length];
    update({ theme: next });
  };

  const version = healthQuery.data?.version ?? "…";
  const [activityOpen, setActivityOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(true);
  const [wandToast, setWandToast] = useState<{ id: number; message: string } | null>(null);
  const nextWandToastId = useRef(0);

  const muiTheme = useTheme();
  const isTablet = useMediaQuery(muiTheme.breakpoints.down("md"));

  // Auto-collapse the nav on tablet — both when the breakpoint changes
  // (rotate/resize) and when the route changes (so the drawer doesn't
  // linger over the new page).
  useEffect(() => {
    if (isTablet) setNavOpen(false);
  }, [isTablet, pathname]);

  const drawerWidth = navOpen ? DRAWER_WIDTH_OPEN : DRAWER_WIDTH_CLOSED;

  useEffect(() => onDownloadSaved((path) => {
    // The user chose the folder in the Save dialog, so name it rather than
    // assuming Downloads.
    const parts = path.split(/[\\/]/).filter(Boolean);
    const name = parts.pop() ?? path;
    const folder = parts.pop();
    setDownloadToast(folder ? `Saved “${name}” to ${folder}` : `Saved “${name}”`);
  }), []);

  useEffect(() => {
    const from = notices.status?.updated_from;
    if (!from || updateSeen.current === from) return;
    updateSeen.current = from;
    setUpdatedToastVersion(notices.status?.current_version ?? null);
    void markVersionSeen();
  }, [notices.status?.current_version, notices.status?.updated_from]);

  // Resolve the user's saved nav order. Re-normalized every render so a
  // fresh settings hydrate (or a new nav item added in a future version)
  // surfaces immediately.
  const reorderableRoutes = useMemo(
    () => normalizeNavOrder(settings?.nav_order),
    [settings?.nav_order],
  );
  const itemByRoute = useMemo(() => {
    const map = new Map<string, NavItem>();
    for (const item of REORDERABLE_ITEMS) map.set(item.to, item);
    return map;
  }, []);

  // Activation distance on PointerSensor disambiguates click-to-navigate
  // from drag-to-reorder: a click that releases within 8 px still fires
  // the NavLink; 8 px or more of pointer movement starts a drag instead.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const dragClickGuard = useMemo(() => createDragClickGuard(), []);
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = reorderableRoutes.indexOf(active.id as string);
    const newIndex = reorderableRoutes.indexOf(over.id as string);
    if (oldIndex < 0 || newIndex < 0) return;
    void update({ nav_order: arrayMove(reorderableRoutes, oldIndex, newIndex) });
  };

  return (
    <WandToastContext.Provider
      value={(message) => {
        nextWandToastId.current += 1;
        setWandToast({ id: nextWandToastId.current, message });
      }}
    >
    <Box sx={{ display: "flex", height: "100dvh" }}>
      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          transition: "width 0.2s",
          "& .MuiDrawer-paper": {
            width: drawerWidth,
            boxSizing: "border-box",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            transition: "width 0.2s",
          },
        }}
      >
        {/* Collapse/expand strip */}
        <Box
          sx={{
            display: "flex",
            justifyContent: navOpen ? "flex-end" : "center",
            bgcolor: "action.hover",
            borderBottom: 1,
            borderColor: "divider",
            py: 0.25,
            px: 0.5,
          }}
        >
          {/* Remounted on each toggle: the button moves under the pointer, so the
              open tooltip would otherwise stay put, pointing at the old spot. */}
          <Tooltip key={navOpen ? "open" : "closed"} title={navOpen ? "Collapse sidebar" : "Expand sidebar"} arrow placement="right">
            <IconButton size="small" onClick={() => setNavOpen(!navOpen)} sx={{ p: 0.25, color: "primary.main" }}>
              {navOpen ? <KeyboardDoubleArrowLeftIcon sx={{ fontSize: 16 }} /> : <KeyboardDoubleArrowRightIcon sx={{ fontSize: 16 }} />}
            </IconButton>
          </Tooltip>
        </Box>

        {/* Header */}
        {navOpen ? (
          <Box sx={{ px: 2, py: 2 }}>
            <Box sx={{ display: "flex", alignItems: "baseline", gap: 1 }}>
              <Typography variant="h6" fontWeight={600} noWrap>
                NightCrate
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap>
                v{version}
              </Typography>
            </Box>
            {activeDbName && (
              <Typography variant="caption" color="text.secondary" noWrap sx={{ display: "block", mt: -0.5 }}>
                {activeDbName}
              </Typography>
            )}
            <NoticesPill status={notices.status} expanded onClick={(event) => setNoticeAnchor(event.currentTarget)} />
          </Box>
        ) : (
          <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", py: 2 }}>
            <Tooltip title="NightCrate" placement="right">
              <Typography variant="h6" fontWeight={600} sx={{ fontSize: 14 }}>
                NC
              </Typography>
            </Tooltip>
            <NoticesPill status={notices.status} expanded={false} onClick={(event) => setNoticeAnchor(event.currentTarget)} />
          </Box>
        )}
        <Divider />

        {/* Navigation: scrolls on its own between the header and the bottom
            bar, so a zoomed-in or short window keeps the bottom bar (and the
            zoom reset) reachable. */}
        <List dense sx={{ flex: "1 1 auto", minHeight: 0, overflowY: "auto" }}>
          {/* Home stays pinned at the top, never reorderable. */}
          <NavItemRow item={HOME_ITEM} navOpen={navOpen} />
          {isTablet ? (
            reorderableRoutes.map((route) => {
              const item = itemByRoute.get(route);
              if (!item) return null;
              return <NavItemRow key={route} item={item} navOpen={navOpen} />;
            })
          ) : (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragStart={dragClickGuard.start}
              onDragEnd={(event) => {
                dragClickGuard.stop();
                handleDragEnd(event);
              }}
              onDragCancel={dragClickGuard.stop}
            >
              <SortableContext items={reorderableRoutes} strategy={verticalListSortingStrategy}>
                {reorderableRoutes.map((route) => {
                  const item = itemByRoute.get(route);
                  if (!item) return null;
                  return <SortableNavItemRow key={route} item={item} navOpen={navOpen} />;
                })}
              </SortableContext>
            </DndContext>
          )}
        </List>

        {/* Bottom controls */}
        <Box
          sx={{
            flexShrink: 0,
            borderTop: 1,
            borderColor: "divider",
            bgcolor: "action.hover",
            display: "flex",
            alignItems: "center",
            gap: 0.5,
            px: navOpen ? 2 : 0,
            py: 1.5,
            justifyContent: navOpen ? "flex-start" : "center",
            flexWrap: "wrap",
          }}
        >
          <Tooltip title={`Theme: ${THEME_LABELS[currentTheme]}`} arrow placement={navOpen ? "top" : "right"}>
            <IconButton size="small" onClick={cycleTheme} sx={{ p: 0.5 }}>
              {THEME_ICONS[currentTheme]}
            </IconButton>
          </Tooltip>
          <Tooltip title="Activity Console" arrow placement={navOpen ? "top" : "right"}>
            <IconButton size="small" onClick={() => setActivityOpen(true)} sx={{ p: 0.5 }}>
              <TimelineIcon sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
          {zoom !== 1 && (
            <Tooltip title={`Back to 100% (${resetZoomShortcut()})`} arrow placement={navOpen ? "top" : "right"}>
              <Button
                size="small"
                onClick={resetZoom}
                sx={{ minWidth: 0, px: 0.75, py: 0, fontSize: 12, lineHeight: "24px", color: "text.secondary" }}
              >
                {Math.round(zoom * 100)}%
              </Button>
            </Tooltip>
          )}
          <Box sx={{ ml: navOpen ? "auto" : 0 }}>
            <EasterEggWand lines={ASTRO_JOKES} tooltip="Words of wisdom" size={16} />
          </Box>
        </Box>
      </Drawer>

      {/* `position: relative` keeps absolutely positioned content (such as a
          visually hidden live region) inside this scroll area; otherwise it is
          placed against the page and the whole window scrolls as well. */}
      <Box component="main" sx={{ flexGrow: 1, overflow: "auto", display: "flex", flexDirection: "column", position: "relative" }}>
        <PersistentPages pathname={pathname} />
      </Box>

      <ActivityConsole open={activityOpen} onClose={() => setActivityOpen(false)} />
      <NoticesPanel anchorEl={noticeAnchor} drawerWidth={drawerWidth} status={notices.status} onClose={() => setNoticeAnchor(null)} onDismiss={(id, action) => void notices.dismiss(id, action)} onInstall={(notice) => { setNoticeAnchor(null); void installFlow.start(notice); }} />
      <UpdateQuestionDialog
        open={notices.status?.check_automatically === null && !questionDismissed}
        onDismiss={() => setQuestionDismissed(true)}
        onAnswer={(answer) => {
          void setCheckAutomatically(answer).then((status) => {
            queryClient.setQueryData(["updates"], status);
            if (answer) void notices.refresh();
          });
          setQuestionDismissed(true);
        }}
      />
      {installFlow.dialog}
      <AppToast
        message={updatedToastVersion ? `Updated to ${updatedToastVersion}.${notices.status?.backup_taken ? " Your workspace was backed up first." : ""}` : null}
        linkLabel="What's new"
        linkHref={`https://github.com/fbaptiste/nightcrate/releases/tag/v${notices.status?.current_version ?? ""}`}
        left={drawerWidth + 16}
        onClose={() => setUpdatedToastVersion(null)}
      />
      <AppToast message={downloadToast} left={drawerWidth + 16} onClose={() => setDownloadToast(null)} />
      <WandToast
        id={wandToast?.id ?? 0}
        message={wandToast?.message ?? null}
        left={drawerWidth + 16}
        onClose={() => setWandToast(null)}
      />
    </Box>
    </WandToastContext.Provider>
  );
}

// Width of the leading drag-handle slot in expanded mode. Hidden
// entirely when the drawer is collapsed so the icon-only mode stays
// compact. Reorderable rows put a DragIndicatorIcon in the slot;
// Home renders an empty slot of the same width so its nav icon
// stays horizontally aligned with the draggable rows' nav icons.
const DRAG_SLOT_WIDTH = 20;

/** Non-draggable nav row — used for Home only. Kept as a tiny helper so
 *  the Home and reorderable rows share identical markup (tooltip,
 *  active-state styling, collapsed-width behavior, drag-slot alignment). */
function NavItemRow({ item, navOpen }: { item: NavItem; navOpen: boolean }) {
  return (
    <ListItem disablePadding>
      <NavLink
        to={item.to}
        end={item.to === "/"}
        style={{ textDecoration: "none", width: "100%", color: "inherit" }}
      >
        {({ isActive }) => (
          <Tooltip title={navOpen ? "" : item.label} placement="right" arrow>
            <ListItemButton
              selected={isActive}
              sx={{ justifyContent: navOpen ? "initial" : "center", px: navOpen ? 1.25 : 1.5 }}
            >
              {navOpen && <Box sx={{ width: DRAG_SLOT_WIDTH, flexShrink: 0 }} />}
              <ListItemIcon sx={{ minWidth: navOpen ? 36 : "auto" }}>{item.icon}</ListItemIcon>
              {navOpen && <ListItemText primary={item.label} />}
            </ListItemButton>
          </Tooltip>
        )}
      </NavLink>
    </ListItem>
  );
}

/** Draggable nav row. Attaches ``useSortable`` to the outer ``ListItem``
 *  and passes the drag listeners onto the whole item — a click (release
 *  within 8 px of pointerdown) still navigates via the NavLink; a
 *  pointerdown + ≥8 px move starts a drag instead. In expanded mode a
 *  subtle DragIndicatorIcon sits in the leading slot as a visual
 *  affordance (fades in on hover); in collapsed mode the indicator is
 *  hidden — the whole row is still draggable, there's just no room for
 *  the icon in the 52-px drawer. */
function SortableNavItemRow({ item, navOpen }: { item: NavItem; navOpen: boolean }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.to,
  });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    // While dragging, lift above siblings so the moving row overlays
    // neighbors instead of being clipped by their background.
    zIndex: isDragging ? 1 : undefined,
    cursor: isDragging ? "grabbing" : undefined,
  };

  return (
    <ListItem ref={setNodeRef} style={style} disablePadding {...attributes} {...listeners}>
      <NavLink
        to={item.to}
        end={item.to === "/"}
        // dnd-kit does the reordering; a native drag of the link or its
        // selected text would start too, and WebKit loads a dropped link.
        draggable={false}
        style={{
          textDecoration: "none",
          width: "100%",
          color: "inherit",
          userSelect: "none",
          WebkitUserDrag: "none",
        } as React.CSSProperties}
      >
        {({ isActive }) => (
          <Tooltip title={navOpen ? "" : item.label} placement="right" arrow>
            <ListItemButton
              selected={isActive}
              sx={{
                justifyContent: navOpen ? "initial" : "center",
                px: navOpen ? 1.25 : 1.5,
                // Reveal the drag indicator at full muted opacity on
                // hover; keep it faint otherwise so the nav doesn't
                // look cluttered at rest.
                "&:hover .drag-indicator": { opacity: 0.6 },
              }}
            >
              {navOpen && (
                <Box
                  className="drag-indicator"
                  sx={{
                    width: DRAG_SLOT_WIDTH,
                    flexShrink: 0,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "text.secondary",
                    opacity: isDragging ? 0.6 : 0.25,
                    transition: "opacity 0.12s",
                  }}
                >
                  <DragIndicatorIcon sx={{ fontSize: 16 }} />
                </Box>
              )}
              <ListItemIcon sx={{ minWidth: navOpen ? 36 : "auto" }}>{item.icon}</ListItemIcon>
              {navOpen && <ListItemText primary={item.label} />}
            </ListItemButton>
          </Tooltip>
        )}
      </NavLink>
    </ListItem>
  );
}

const PERSISTENT_ROUTES: Record<string, React.ComponentType> = {
  "/image-analyzer": ImageAnalyzerPage,
  "/planner": PlannerPage,
  "/phd2-analyzer": Phd2AnalyzerPage,
  "/catalog/dso": DsoCatalogPage,
  "/weather": WeatherPage,
  "/gallery": GalleryPage,
  "/messier": MessierPage,
};

const persistentPaths = Object.keys(PERSISTENT_ROUTES);

function PersistentPages({ pathname }: { pathname: string }) {
  const [mounted, setMounted] = useState<Set<string>>(() => new Set());

  const isOnPersistent = persistentPaths.includes(pathname);

  useEffect(() => {
    if (isOnPersistent && !mounted.has(pathname)) {
      setMounted((prev) => new Set([...prev, pathname]));
    }
    // `mounted` is deliberately read as the current route-entry guard; adding it
    // would make the mounting effect rerun after its own state update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, isOnPersistent]);

  return (
    <>
      {persistentPaths.map((path) => {
        if (!mounted.has(path)) return null;
        const Component = PERSISTENT_ROUTES[path];
        return (
          <Box
            key={path}
            sx={{
              display: pathname === path ? "flex" : "none",
              flexDirection: "column",
              flexGrow: 1,
              minHeight: 0,
            }}
          >
            <PageErrorBoundary resetKey={pathname}>
              <Component />
            </PageErrorBoundary>
          </Box>
        );
      })}
      {!isOnPersistent && <Outlet />}
    </>
  );
}
