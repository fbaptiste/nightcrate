import { useParams, useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import { EquipmentSidebar } from "@/components/equipment/EquipmentSidebar";
import { EquipmentPlaceholder } from "@/components/equipment/EquipmentPlaceholder";
import CameraList from "@/components/equipment/CameraList";
import TelescopeList from "@/components/equipment/TelescopeList";
import FilterList from "@/components/equipment/FilterList";

export function EquipmentPage() {
  const { category = "cameras" } = useParams();
  const navigate = useNavigate();

  const content = (() => {
    switch (category) {
      case "cameras":
        return <CameraList />;
      case "telescopes":
        return <TelescopeList />;
      case "filters":
        return <FilterList />;
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
