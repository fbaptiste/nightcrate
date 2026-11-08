import type { RefObject } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import GpsFixedIcon from "@mui/icons-material/GpsFixed";
import { Link as RouterLink } from "react-router-dom";
import type { GalleryItem } from "@/api/gallery";
import NameWithAlternates from "@/components/common/NameWithAlternates";
import { formatHoursMinutes } from "@/components/projects/IntegrationBars";
import { formatImagingRuns, tileImageUrl } from "@/lib/galleryRendition";
import ExpandButton from "./ExpandButton";
import GalleryImage from "./GalleryImage";
import RigSummary from "./RigSummary";
import StatusPills from "./StatusPills";

interface Props {
  items: GalleryItem[];
  ws: string;
  onExpand: (id: number) => void;
  expandRefs: RefObject<Map<number, HTMLButtonElement>>;
}

interface RowProps {
  item: GalleryItem;
  index: number;
  ws: string;
  onExpand: (id: number) => void;
  expandRefs: RefObject<Map<number, HTMLButtonElement>>;
}

function GalleryListRow({ item, index, ws, onExpand, expandRefs }: RowProps) {
  const runs = formatImagingRuns(item);
  const imageId = item.main_image_id;
  const src = tileImageUrl(item, "small", 180, window.devicePixelRatio || 1, ws);
  const foundLabel =
    `Found in this project's plate-solved image: ${item.found_in_image.join(", ")}`;
  const dates = runs.length
    ? `${runs.join(", ")}, ${item.nights} ${item.nights === 1 ? "night" : "nights"}`
    : "No imaging dates";
  const integration = item.integration_minutes
    ? formatHoursMinutes(item.integration_minutes)
    : "None recorded";

  const registerExpandButton = (button: HTMLButtonElement | null) => {
    if (button) expandRefs.current.set(item.project_id, button);
    else expandRefs.current.delete(item.project_id);
  };

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "180px 1fr",
        gap: "20px",
        py: "16px",
        borderBottom: 1,
        borderColor: "divider",
        ...(index === 0 ? { pt: 0 } : {}),
      }}
    >
      <Box
        sx={{
          position: "relative",
          width: 180,
          aspectRatio: "4 / 3",
          bgcolor: "common.black",
          borderRadius: "6px",
          overflow: "hidden",
        }}
      >
        {src ? (
          <GalleryImage src={src} alt={item.name} />
        ) : (
          <Box
            sx={{
              display: "grid",
              placeItems: "center",
              height: "100%",
              color: "#8e8c88",
              fontSize: 13,
            }}
          >
            No main image
          </Box>
        )}
        {item.found_in_image.length > 0 && (
          <Box
            aria-label={foundLabel}
            sx={{
              position: "absolute",
              left: 6,
              bottom: 6,
              maxWidth: "calc(100% - 12px)",
              height: 22,
              px: "7px",
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
              borderRadius: 12,
              bgcolor: "rgba(0, 0, 0, 0.62)",
              border: "1px solid rgba(255, 255, 255, 0.28)",
              color: "common.white",
              fontSize: 11,
              fontWeight: 600,
              whiteSpace: "nowrap",
              overflow: "hidden",
              pointerEvents: "none",
            }}
          >
            <GpsFixedIcon sx={{ fontSize: 13 }} />
            In image: {item.found_in_image[0]}
            {item.found_in_image.length > 1
              ? ` +${item.found_in_image.length - 1}`
              : ""}
          </Box>
        )}
        {imageId != null && (
          <ExpandButton
            buttonRef={registerExpandButton}
            label={`View ${item.name} full size`}
            onClick={() => onExpand(item.project_id)}
            size="compact"
          />
        )}
      </Box>
      <Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: "10px", mb: "6px" }}>
          <Link
            component={RouterLink}
            to={`/projects/${item.project_id}`}
            underline="hover"
            color="text.primary"
            sx={{ fontSize: 16, fontWeight: 600 }}
          >
            {item.name}
          </Link>
          <StatusPills status={item.status} retired={item.retired} />
        </Box>
        <Box
          component="dl"
          sx={{
            m: 0,
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            gap: "4px 16px",
            fontSize: 14,
          }}
        >
          <Box component="dt" sx={{ color: "text.secondary" }}>
            Targets
          </Box>
          <Box
            component="dd"
            sx={{ m: 0, display: "flex", flexWrap: "wrap", gap: "6px" }}
          >
            {item.targets.length ? (
              item.targets.map((target) => (
                <NameWithAlternates
                  key={target.dso_id}
                  name={target.name}
                  otherNames={target.also_known_as}
                >
                  <Chip
                    variant="outlined"
                    size="small"
                    label={target.name}
                    sx={{ height: 22, fontSize: 12 }}
                  />
                </NameWithAlternates>
              ))
            ) : (
              <Box sx={{ color: "text.secondary" }}>No targets</Box>
            )}
          </Box>
          <Box component="dt" sx={{ color: "text.secondary" }}>
            Imaging dates
          </Box>
          <Box
            component="dd"
            sx={{ m: 0, color: runs.length ? "text.primary" : "text.secondary" }}
          >
            {dates}
          </Box>
          <Box component="dt" sx={{ color: "text.secondary" }}>
            Integration
          </Box>
          <Box
            component="dd"
            sx={{
              m: 0,
              color: item.integration_minutes ? "text.primary" : "text.secondary",
            }}
          >
            {integration}
          </Box>
          <Box component="dt" sx={{ color: "text.secondary" }}>
            Rigs
          </Box>
          <Box component="dd" sx={{ m: 0 }}>
            <RigSummary rigs={item.rigs} />
          </Box>
        </Box>
      </Box>
    </Box>
  );
}

export default function GalleryList({ items, ws, onExpand, expandRefs }: Props) {
  return (
    <Box sx={{ maxWidth: 980 }}>
      {items.map((item, index) => (
        <GalleryListRow
          key={item.project_id}
          item={item}
          index={index}
          ws={ws}
          onExpand={onExpand}
          expandRefs={expandRefs}
        />
      ))}
    </Box>
  );
}
