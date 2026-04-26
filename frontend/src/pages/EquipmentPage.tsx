import { useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
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
  const [ownedOnly, setOwnedOnly] = useState(false);

  const lastCategory = useRef<string | null>(null);
  if (lastCategory.current !== category) {
    lastCategory.current = category;
    setActivity(`Equipment — ${formatCategoryLabel(category)}`);
  }

  const hasOwnedToggle = !["sensors", "manufacturers", "lookup-tables"].includes(category);

  const content = (() => {
    switch (category) {
      case "cameras":
        return <CameraList mineOnly={ownedOnly} />;
      case "telescopes":
        return <TelescopeList mineOnly={ownedOnly} />;
      case "filters":
        return <FilterList mineOnly={ownedOnly} />;
      case "sensors":
        return <SensorList />;
      case "mounts":
        return <MountList mineOnly={ownedOnly} />;
      case "focusers":
        return <FocuserList mineOnly={ownedOnly} />;
      case "filter-wheels":
        return <FilterWheelList mineOnly={ownedOnly} />;
      case "oags":
        return <OagList mineOnly={ownedOnly} />;
      case "guide-scopes":
        return <GuideScopeList mineOnly={ownedOnly} />;
      case "computers":
        return <ComputerList mineOnly={ownedOnly} />;
      case "software":
        return <SoftwareList mineOnly={ownedOnly} />;
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
        {hasOwnedToggle && (
          <Box sx={{ mb: 1.5 }}>
            <ToggleButtonGroup
              size="small"
              exclusive
              value={ownedOnly ? "owned" : "all"}
              onChange={(_, v) => { if (v) setOwnedOnly(v === "owned"); }}
            >
              <ToggleButton value="all" sx={{ px: 1.5, py: 0.25, fontSize: "0.75rem" }}>All</ToggleButton>
              <ToggleButton value="owned" sx={{ px: 1.5, py: 0.25, fontSize: "0.75rem" }}>Owned</ToggleButton>
            </ToggleButtonGroup>
          </Box>
        )}
        {content}
      </Box>
    </Box>
  );
}
