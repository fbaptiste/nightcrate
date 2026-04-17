import { useQuery } from "@tanstack/react-query";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { fetchMineCounts, type MineCounts } from "@/api/equipment";

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
      { id: "telescopes", label: "OTAs" },
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
  const { data: mineCounts } = useQuery<MineCounts>({
    queryKey: ["mine-counts"],
    queryFn: fetchMineCounts,
  });

  const MINE_ITEMS: Array<{ id: string; label: string; countKey: keyof MineCounts }> = [
    { id: "my-cameras", label: "Cameras", countKey: "cameras" },
    { id: "my-telescopes", label: "OTAs", countKey: "telescopes" },
    { id: "my-filters", label: "Filters", countKey: "filters" },
    { id: "my-mounts", label: "Mounts", countKey: "mounts" },
    { id: "my-focusers", label: "Focusers", countKey: "focusers" },
    { id: "my-filter-wheels", label: "Filter Wheels", countKey: "filter_wheels" },
    { id: "my-oags", label: "OAGs", countKey: "oags" },
    { id: "my-guide-scopes", label: "Guide Scopes", countKey: "guide_scopes" },
    { id: "my-computers", label: "Computers", countKey: "computers" },
    { id: "my-software", label: "Software", countKey: "software" },
  ];

  const visibleMineItems = MINE_ITEMS.filter(
    (it) => (mineCounts?.[it.countKey] ?? 0) > 0,
  );
  const totalMine = mineCounts
    ? Object.values(mineCounts).reduce((s, n) => s + n, 0)
    : 0;

  const defaultExpanded = ["group-my-equipment", ...GROUPS.map((g) => g.id)];

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
          if (itemId && !itemId.startsWith("group-") && itemId !== "my-empty-hint") {
            onSelectCategory(itemId);
          }
        }}
      >
        <TreeItem
          itemId="group-my-equipment"
          label={
            <Typography
              variant="caption"
              fontWeight={700}
              sx={{
                textTransform: "uppercase",
                letterSpacing: 0.8,
                color: "text.secondary",
              }}
            >
              My Equipment
            </Typography>
          }
        >
          {totalMine === 0 ? (
            <TreeItem
              itemId="my-empty-hint"
              disabled
              label={
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ fontStyle: "italic", lineHeight: 1.4, display: "block", py: 0.5 }}
                >
                  Click the star on any equipment row to add it here.
                </Typography>
              }
            />
          ) : (
            visibleMineItems.map((item) => (
              <TreeItem key={item.id} itemId={item.id} label={item.label} />
            ))
          )}
        </TreeItem>
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
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", px: 2, pt: 2, pb: 1, fontStyle: "italic", lineHeight: 1.4 }}
      >
        Seed data was AI-generated. Please verify your equipment specs for accuracy.
      </Typography>
    </Box>
  );
}
