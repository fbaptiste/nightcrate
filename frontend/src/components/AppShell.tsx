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
import DarkModeIcon from "@mui/icons-material/DarkMode";
import DesktopWindowsIcon from "@mui/icons-material/DesktopWindows";
import HomeIcon from "@mui/icons-material/Home";
import ImageSearchIcon from "@mui/icons-material/ImageSearch";
import LightModeIcon from "@mui/icons-material/LightMode";
import CodeIcon from "@mui/icons-material/Code";
import SettingsIcon from "@mui/icons-material/Settings";
import { NavLink, Outlet } from "react-router-dom";
import { fetchHealth } from "@/api/files";
import { useSettingsStore } from "@/stores/settingsStore";
import type { Theme } from "@/api/settings";

const DRAWER_WIDTH = 220;

const navItems = [
  { to: "/", label: "Home", icon: <HomeIcon /> },
  { to: "/image-viewer", label: "Image Viewer", icon: <ImageSearchIcon /> },
  { to: "/settings", label: "Settings", icon: <SettingsIcon /> },
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

export function AppShell() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    staleTime: Infinity,
  });
  const { settings, update } = useSettingsStore();
  const currentTheme: Theme = settings?.theme ?? "browser";

  const cycleTheme = () => {
    const idx = THEME_CYCLE.indexOf(currentTheme);
    const next = THEME_CYCLE[(idx + 1) % THEME_CYCLE.length];
    update({ theme: next });
  };

  const version = healthQuery.data?.version ?? "…";

  return (
    <Box sx={{ display: "flex", height: "100vh" }}>
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: DRAWER_WIDTH,
            boxSizing: "border-box",
            display: "flex",
            flexDirection: "column",
          },
        }}
      >
        <Box sx={{ px: 2, py: 2 }}>
          <Typography variant="h6" fontWeight={600} noWrap>
            NightCrate
          </Typography>
        </Box>
        <Divider />
        <List dense>
          {navItems.map(({ to, label, icon }) => (
            <ListItem key={to} disablePadding>
              <NavLink
                to={to}
                end={to === "/"}
                style={{ textDecoration: "none", width: "100%", color: "inherit" }}
              >
                {({ isActive }) => (
                  <ListItemButton selected={isActive}>
                    <ListItemIcon sx={{ minWidth: 36 }}>{icon}</ListItemIcon>
                    <ListItemText primary={label} />
                  </ListItemButton>
                )}
              </NavLink>
            </ListItem>
          ))}
        </List>

        {/* Spacer pushes version to bottom */}
        <Box sx={{ flexGrow: 1 }} />

        {/* Version + theme toggle */}
        <Box sx={{ px: 2, py: 1.5, borderTop: 1, borderColor: "divider", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Typography variant="caption" color="text.secondary">
            v{version}
          </Typography>
          <Tooltip title={`Theme: ${THEME_LABELS[currentTheme]} — click to cycle`} arrow>
            <IconButton size="small" onClick={cycleTheme} sx={{ p: 0.5 }}>
              {THEME_ICONS[currentTheme]}
            </IconButton>
          </Tooltip>
        </Box>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, overflow: "auto", display: "flex", flexDirection: "column" }}>
        <Outlet />
      </Box>
    </Box>
  );
}
