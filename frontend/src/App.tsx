import { useEffect } from "react";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/ThemeProvider";
import { AppShell } from "@/components/AppShell";
import { HomePage } from "@/pages/HomePage";
import { ImageViewerPage } from "@/pages/ImageViewerPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ApiDocsPage } from "@/pages/ApiDocsPage";
import { EquipmentPage } from "@/pages/EquipmentPage";
import { AdminPage } from "@/pages/AdminPage";
import LocationsPage from "@/pages/LocationsPage";
import RigsPage from "@/pages/RigsPage";
import CalculatorsPage from "@/pages/CalculatorsPage";
import DsoCatalogPage from "@/pages/DsoCatalogPage";
import PlannerPage from "@/pages/PlannerPage";
import WeatherPage from "./pages/WeatherPage";
import { useSettingsStore } from "@/stores/settingsStore";
import { fetchHealth } from "@/api/admin";
import { SetupWizard } from "@/components/SetupWizard";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "image-viewer", element: <ImageViewerPage /> },
      { path: "equipment", element: <EquipmentPage /> },
      { path: "equipment/:category", element: <EquipmentPage /> },
      { path: "locations", element: <LocationsPage /> },
      { path: "rigs", element: <RigsPage /> },
      { path: "weather", element: <WeatherPage /> },
      { path: "calculators", element: <CalculatorsPage /> },
      { path: "calculators/:calcId", element: <CalculatorsPage /> },
      { path: "catalog/dso", element: <DsoCatalogPage /> },
      { path: "planner", element: <PlannerPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "admin", element: <AdminPage /> },
      { path: "api-docs", element: <ApiDocsPage /> },
    ],
  },
]);

function AppContent() {
  const load = useSettingsStore((s) => s.load);
  const { data: health, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  useEffect(() => {
    if (health?.db_configured) {
      load();
    }
  }, [health?.db_configured, load]);

  if (isLoading) return null;
  if (!health?.db_configured) return <SetupWizard />;

  return <RouterProvider router={router} />;
}

export default function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  );
}
