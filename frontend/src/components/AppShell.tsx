import { useRef, useState } from "react";
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
import PublicIcon from "@mui/icons-material/Public";
import PlaceIcon from "@mui/icons-material/Place";
import PrecisionManufacturingIcon from "@mui/icons-material/PrecisionManufacturing";
import SettingsIcon from "@mui/icons-material/Settings";
import StarsIcon from "@mui/icons-material/Stars";
import WbSunnyIcon from "@mui/icons-material/WbSunny";
import TimelineIcon from "@mui/icons-material/Timeline";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { fetchHealth } from "@/api/files";
import { fetchAdminStatus } from "@/api/admin";
import { setActivity } from "@/api/client";
import { useSettingsStore } from "@/stores/settingsStore";
import { ActivityConsole } from "@/components/ActivityConsole";
import type { Theme } from "@/api/settings";

const DRAWER_WIDTH_OPEN = 220;
const DRAWER_WIDTH_CLOSED = 52;

const navItems = [
  { to: "/", label: "Home", icon: <HomeIcon /> },
  { to: "/image-viewer", label: "Image Viewer", icon: <ImageSearchIcon /> },
  { to: "/locations", label: "Locations", icon: <PlaceIcon /> },
  { to: "/weather", label: "Weather", icon: <WbSunnyIcon /> },
  { to: "/rigs", label: "Rigs", icon: <PrecisionManufacturingIcon /> },
  { to: "/equipment", label: "Equipment", icon: <BuildIcon /> },
  { to: "/calculators", label: "Calculators", icon: <CalculateOutlinedIcon /> },
  { to: "/planner", label: "Planner", icon: <StarsIcon /> },
  { to: "/catalog/dso", label: "DSO Catalog", icon: <PublicIcon /> },
  { to: "/settings", label: "Settings", icon: <SettingsIcon /> },
  { to: "/admin", label: "Admin", icon: <AdminPanelSettingsIcon /> },
  { to: "/api-docs", label: "API Docs", icon: <CodeIcon /> },
];

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
  const match = navItems.find((n) =>
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
          {navItems.map(({ to, label, icon }) => (
            <ListItem key={to} disablePadding>
              <NavLink
                to={to}
                end={to === "/"}
                style={{ textDecoration: "none", width: "100%", color: "inherit" }}
              >
                {({ isActive }) => (
                  <Tooltip title={navOpen ? "" : label} placement="right" arrow>
                    <ListItemButton
                      selected={isActive}
                      sx={{ justifyContent: navOpen ? "initial" : "center", px: navOpen ? 2 : 1.5 }}
                    >
                      <ListItemIcon sx={{ minWidth: navOpen ? 36 : "auto" }}>{icon}</ListItemIcon>
                      {navOpen && <ListItemText primary={label} />}
                    </ListItemButton>
                  </Tooltip>
                )}
              </NavLink>
            </ListItem>
          ))}
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
