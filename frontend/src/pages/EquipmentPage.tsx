import { useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import { setActivity } from "@/api/client";
import { EquipmentSidebar } from "@/components/equipment/EquipmentSidebar";
import { EquipmentPlaceholder } from "@/components/equipment/EquipmentPlaceholder";
import CameraList from "@/components/equipment/CameraList";
import TelescopeList from "@/components/equipment/TelescopeList";
import FilterList from "@/components/equipment/FilterList";
import SensorList from "@/components/equipment/SensorList";
import MountList from "@/components/equipment/MountList";
import FocuserList from "@/components/equipment/FocuserList";
import FilterWheelList from "@/components/equipment/FilterWheelList";
import OagList from "@/components/equipment/OagList";
import GuideScopeList from "@/components/equipment/GuideScopeList";
import ComputerList from "@/components/equipment/ComputerList";
import SoftwareList from "@/components/equipment/SoftwareList";
import ManufacturerList from "@/components/equipment/ManufacturerList";
import LookupTablesPanel from "@/components/equipment/LookupTablesPanel";

function formatCategoryLabel(category: string): string {
  return category
    .split("-")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ");
}

export function EquipmentPage() {
  const { category = "cameras" } = useParams();
  const navigate = useNavigate();

  // Refine the page-level activity label to include the sub-category so the
  // Activity Console groups requests like "Equipment — Cameras" separately.
  const lastCategory = useRef<string | null>(null);
  if (lastCategory.current !== category) {
    lastCategory.current = category;
    setActivity(`Equipment — ${formatCategoryLabel(category)}`);
  }

  const content = (() => {
    switch (category) {
      case "cameras":
        return <CameraList />;
      case "my-cameras":
        return <CameraList mineOnly />;
      case "telescopes":
        return <TelescopeList />;
      case "my-telescopes":
        return <TelescopeList mineOnly />;
      case "filters":
        return <FilterList />;
      case "my-filters":
        return <FilterList mineOnly />;
      case "sensors":
        return <SensorList />;
      case "mounts":
        return <MountList />;
      case "my-mounts":
        return <MountList mineOnly />;
      case "focusers":
        return <FocuserList />;
      case "my-focusers":
        return <FocuserList mineOnly />;
      case "filter-wheels":
        return <FilterWheelList />;
      case "my-filter-wheels":
        return <FilterWheelList mineOnly />;
      case "oags":
        return <OagList />;
      case "my-oags":
        return <OagList mineOnly />;
      case "guide-scopes":
        return <GuideScopeList />;
      case "my-guide-scopes":
        return <GuideScopeList mineOnly />;
      case "computers":
        return <ComputerList />;
      case "my-computers":
        return <ComputerList mineOnly />;
      case "software":
        return <SoftwareList />;
      case "my-software":
        return <SoftwareList mineOnly />;
      case "manufacturers":
        return <ManufacturerList />;
      case "lookup-tables":
        return <LookupTablesPanel />;
      default:
        return <EquipmentPlaceholder category={category} />;
    }
  })();

  return (
    <Box sx={{ display: "flex", height: "100%" }}>
      <EquipmentSidebar
        selectedCategory={category}
        onSelectCategory={(cat) => navigate(`/equipment/${cat}`)}
      />
      <Box sx={{ flex: 1, overflow: "auto", p: 2 }}>
        {content}
      </Box>
    </Box>
  );
}
