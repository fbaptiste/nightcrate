import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

interface EquipmentSidebarProps {
  selectedCategory: string;
  onSelectCategory: (slug: string) => void;
}

const GROUPS = [
  {
    id: "group-imaging",
    label: "Imaging",
    items: [
      { id: "cameras", label: "Cameras" },
      { id: "sensors", label: "Sensors" },
    ],
  },
  {
    id: "group-optics",
    label: "Optics",
    items: [
      { id: "telescopes", label: "Telescopes" },
      { id: "filters", label: "Filters" },
    ],
  },
  {
    id: "group-tracking",
    label: "Tracking",
    items: [{ id: "mounts", label: "Mounts" }],
  },
  {
    id: "group-accessories",
    label: "Accessories",
    items: [
      { id: "focusers", label: "Focusers" },
      { id: "filter-wheels", label: "Filter Wheels" },
      { id: "oags", label: "OAGs" },
      { id: "guide-scopes", label: "Guide Scopes" },
    ],
  },
  {
    id: "group-computing",
    label: "Computing",
    items: [
      { id: "computers", label: "Computers" },
      { id: "software", label: "Software" },
    ],
  },
  {
    id: "group-reference",
    label: "Reference",
    items: [
      { id: "manufacturers", label: "Manufacturers" },
      { id: "lookup-tables", label: "Lookup Tables" },
    ],
  },
];

export function EquipmentSidebar({
  selectedCategory,
  onSelectCategory,
}: EquipmentSidebarProps) {
  const defaultExpanded = GROUPS.map((g) => g.id);

  return (
    <Box
      sx={{
        width: 240,
        flexShrink: 0,
        borderRight: 1,
        borderColor: "divider",
        overflowY: "auto",
        py: 1,
      }}
    >
      <SimpleTreeView
        defaultExpandedItems={defaultExpanded}
        selectedItems={selectedCategory}
        onSelectedItemsChange={(_event, itemId) => {
          if (itemId && !itemId.startsWith("group-")) {
            onSelectCategory(itemId);
          }
        }}
      >
        {GROUPS.map((group) => (
          <TreeItem
            key={group.id}
            itemId={group.id}
            label={
              <Typography
                variant="caption"
                fontWeight={700}
                sx={{ textTransform: "uppercase", letterSpacing: 0.8, color: "text.secondary" }}
              >
                {group.label}
              </Typography>
            }
          >
            {group.items.map((item) => (
              <TreeItem key={item.id} itemId={item.id} label={item.label} />
            ))}
          </TreeItem>
        ))}
      </SimpleTreeView>
    </Box>
  );
}
