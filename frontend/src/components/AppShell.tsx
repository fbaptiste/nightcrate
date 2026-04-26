import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
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
import PublicIcon from "@mui/icons-material/Public";
import PlaceIcon from "@mui/icons-material/Place";
import PrecisionManufacturingIcon from "@mui/icons-material/PrecisionManufacturing";
import SettingsIcon from "@mui/icons-material/Settings";
import StarsIcon from "@mui/icons-material/Stars";
import NightsStayIcon from "@mui/icons-material/NightsStay";
import WbSunnyIcon from "@mui/icons-material/WbSunny";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import TimelineIcon from "@mui/icons-material/Timeline";
import { NavLink, Outlet, useLocation } from "react-router-dom";
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
import { ActivityConsole } from "@/components/ActivityConsole";
import type { Theme } from "@/api/settings";

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
  { to: "/image-viewer", label: "Image Viewer", icon: <ImageSearchIcon /> },
  { to: "/phd2-analyzer", label: "PHD2 Analyzer", icon: <ShowChartIcon /> },
  { to: "/catalog/dso", label: "DSO Catalog", icon: <PublicIcon /> },
  { to: "/calculators", label: "Calculators", icon: <CalculateOutlinedIcon /> },
  { to: "/locations", label: "Locations", icon: <PlaceIcon /> },
  { to: "/rigs", label: "Rigs", icon: <PrecisionManufacturingIcon /> },
  { to: "/equipment", label: "Equipment", icon: <BuildIcon /> },
  { to: "/settings", label: "Settings", icon: <SettingsIcon /> },
  { to: "/admin", label: "Admin", icon: <AdminPanelSettingsIcon /> },
  { to: "/api-docs", label: "API Docs", icon: <CodeIcon /> },
];

const ALL_NAV_ITEMS: NavItem[] = [HOME_ITEM, ...REORDERABLE_ITEMS];

/** Drop unknown routes, then append any reorderable route that was
 *  missing from the saved list. Mirrors ``normalizeClockOrder`` in
 *  ClocksCalc so adding a new nav item in a future version always
 *  surfaces at the end of whatever order the user had saved. */
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
  for (const item of REORDERABLE_ITEMS) {
    if (!seen.has(item.to)) out.push(item.to);
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
  if (lastPathname.current !== pathname) {
    lastPathname.current = pathname;
    setActivity(resolvePageLabel(pathname));
  }

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    staleTime: Infinity,
  });
  const statusQuery = useQuery({
    queryKey: ["admin-status"],
    queryFn: fetchAdminStatus,
    staleTime: 60_000,
  });
  const activeDbName = statusQuery.data?.active_db?.name;
  const { settings, update } = useSettingsStore();
  const currentTheme: Theme = settings?.theme ?? "browser";

  const cycleTheme = () => {
    const idx = THEME_CYCLE.indexOf(currentTheme);
    const next = THEME_CYCLE[(idx + 1) % THEME_CYCLE.length];
    update({ theme: next });
  };

  const version = healthQuery.data?.version ?? "…";
  const [activityOpen, setActivityOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(true);

  const drawerWidth = navOpen ? DRAWER_WIDTH_OPEN : DRAWER_WIDTH_CLOSED;

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

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = reorderableRoutes.indexOf(active.id as string);
    const newIndex = reorderableRoutes.indexOf(over.id as string);
    if (oldIndex < 0 || newIndex < 0) return;
    void update({ nav_order: arrayMove(reorderableRoutes, oldIndex, newIndex) });
  };

  return (
    <Box sx={{ display: "flex", height: "100vh" }}>
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
          <Tooltip title={navOpen ? "Collapse sidebar" : "Expand sidebar"} arrow placement="right">
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
          </Box>
        ) : (
          <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
            <Tooltip title="NightCrate" placement="right">
              <Typography variant="h6" fontWeight={600} sx={{ fontSize: 14 }}>
                NC
              </Typography>
            </Tooltip>
          </Box>
        )}
        <Divider />

        {/* Navigation */}
        <List dense>
          {/* Home stays pinned at the top, never reorderable. */}
          <NavItemRow item={HOME_ITEM} navOpen={navOpen} />
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext items={reorderableRoutes} strategy={verticalListSortingStrategy}>
              {reorderableRoutes.map((route) => {
                const item = itemByRoute.get(route);
                if (!item) return null;
                return <SortableNavItemRow key={route} item={item} navOpen={navOpen} />;
              })}
            </SortableContext>
          </DndContext>
        </List>

        <Box sx={{ flexGrow: 1 }} />

        {/* Bottom controls */}
        <Box
          sx={{
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
        </Box>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, overflow: "auto", display: "flex", flexDirection: "column" }}>
        <Outlet />
      </Box>

      <ActivityConsole open={activityOpen} onClose={() => setActivityOpen(false)} />
    </Box>
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
        style={{ textDecoration: "none", width: "100%", color: "inherit" }}
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
