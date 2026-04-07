import { useParams, useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import { EquipmentSidebar } from "@/components/equipment/EquipmentSidebar";
import { EquipmentPlaceholder } from "@/components/equipment/EquipmentPlaceholder";

// CameraList, TelescopeList, FilterList will be created in Tasks 10-12.
// For now, all categories use placeholders.

export function EquipmentPage() {
  const { category = "cameras" } = useParams();
  const navigate = useNavigate();

  const content = <EquipmentPlaceholder category={category} />;

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
