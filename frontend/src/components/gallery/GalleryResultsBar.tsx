import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import AppsIcon from "@mui/icons-material/Apps";
import CropLandscapeIcon from "@mui/icons-material/CropLandscape";
import GridViewIcon from "@mui/icons-material/GridView";
import ViewListIcon from "@mui/icons-material/ViewList";
import type { GalleryView } from "@/api/settings";
import ViewToggle, { type ViewToggleOption } from "@/components/common/ViewToggle";
import type { GallerySort } from "@/stores/galleryStore";

const VIEW_OPTIONS: ViewToggleOption<GalleryView>[] = [
  { value: "list", label: "List", icon: <ViewListIcon /> },
  { value: "small", label: "Small pictures", icon: <AppsIcon /> },
  { value: "medium", label: "Medium pictures", icon: <GridViewIcon /> },
  { value: "large", label: "Large pictures", icon: <CropLandscapeIcon /> },
];

interface Props {
  count: number;
  sort: GallerySort;
  desc: boolean;
  view: GalleryView;
  onSort: (sort: GallerySort) => void;
  onDirection: () => void;
  onView: (view: GalleryView) => void;
}

export default function GalleryResultsBar({
  count,
  sort,
  desc,
  view,
  onSort,
  onDirection,
  onView,
}: Props) {
  let direction: string;
  if (sort === "name") {
    direction = desc ? "Z to A" : "A to Z";
  } else {
    direction = desc ? "Newest first" : "Oldest first";
  }

  return (
    <Box
      sx={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "12px 24px",
        py: "10px",
        pb: "18px",
        borderTop: 1,
        borderColor: "divider",
      }}
    >
      <Box sx={{ fontWeight: 600 }}>
        {count} {count === 1 ? "project" : "projects"}
      </Box>
      <Box sx={{ flex: 1 }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: "6px" }}>
        <FormControl size="small" sx={{ width: 220 }}>
          <InputLabel>Sort by</InputLabel>
          <Select
            label="Sort by"
            value={sort}
            onChange={(event) => onSort(event.target.value as GallerySort)}
          >
            <MenuItem value="latest">Latest imaging date</MenuItem>
            <MenuItem value="first">First imaging date</MenuItem>
            <MenuItem value="name">Name</MenuItem>
          </Select>
        </FormControl>
        <IconButton
          aria-label={direction}
          title={direction}
          onClick={onDirection}
          sx={{
            width: 36,
            height: 36,
            border: 1,
            borderColor: "divider",
            borderRadius: "6px",
          }}
        >
          {desc ? (
            <ArrowDownwardIcon fontSize="small" />
          ) : (
            <ArrowUpwardIcon fontSize="small" />
          )}
        </IconButton>
      </Box>
      <ViewToggle
        options={VIEW_OPTIONS}
        value={view}
        onChange={onView}
        ariaLabel="Gallery view"
      />
    </Box>
  );
}
