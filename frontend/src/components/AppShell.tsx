import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import HomeIcon from "@mui/icons-material/Home";
import ImageSearchIcon from "@mui/icons-material/ImageSearch";
import SettingsIcon from "@mui/icons-material/Settings";
import { NavLink, Outlet } from "react-router-dom";
import { fetchHealth } from "@/api/files";

const DRAWER_WIDTH = 220;

const navItems = [
  { to: "/", label: "Home", icon: <HomeIcon /> },
  { to: "/image-viewer", label: "Image Viewer", icon: <ImageSearchIcon /> },
  { to: "/settings", label: "Settings", icon: <SettingsIcon /> },
];

export function AppShell() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    staleTime: Infinity,
  });

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

        {/* Version */}
        <Box sx={{ px: 2, py: 1.5, borderTop: 1, borderColor: "divider" }}>
          <Typography variant="caption" color="text.secondary">
            v{version}
          </Typography>
        </Box>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, overflow: "auto", display: "flex", flexDirection: "column" }}>
        <Outlet />
      </Box>
    </Box>
  );
}
