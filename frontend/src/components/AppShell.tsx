import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import { NavLink, Outlet } from "react-router-dom";
import { fetchHealth } from "@/api/files";

const DRAWER_WIDTH = 200;

const navItems = [
  { to: "/", label: "Home" },
  { to: "/fits-viewer", label: "FITS Viewer" },
  { to: "/settings", label: "Settings" },
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
          {navItems.map(({ to, label }) => (
            <ListItem key={to} disablePadding>
              <NavLink
                to={to}
                end={to === "/"}
                style={{ textDecoration: "none", width: "100%", color: "inherit" }}
              >
                {({ isActive }) => (
                  <ListItemButton selected={isActive}>
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
