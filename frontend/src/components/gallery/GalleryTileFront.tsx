import type { RefObject } from "react";
import Box from "@mui/material/Box";
import GpsFixedIcon from "@mui/icons-material/GpsFixed";
import type { GalleryItem } from "@/api/gallery";
import type { CropSize } from "@/api/projects";
import { tileImageUrl } from "@/lib/galleryRendition";
import ExpandButton from "./ExpandButton";
import GalleryImage from "./GalleryImage";

interface Props {
  item: GalleryItem;
  ws: string;
  slotWidth: number;
  cropSize: CropSize;
  small: boolean;
  turned: boolean;
  onTurn: () => void;
  onExpand: () => void;
  buttonRef: RefObject<HTMLButtonElement | null>;
  expandRef: RefObject<HTMLButtonElement | null>;
}

export default function GalleryTileFront({
  item,
  ws,
  slotWidth,
  cropSize,
  small,
  turned,
  onTurn,
  onExpand,
  buttonRef,
  expandRef,
}: Props) {
  const imageId = item.main_image_id;
  const src = tileImageUrl(
    item,
    cropSize,
    slotWidth,
    window.devicePixelRatio || 1,
    ws,
  );
  const foundLabel =
    `Found in this project's plate-solved image: ${item.found_in_image.join(", ")}`;

  return (
    <Box
      inert={turned ? true : undefined}
      aria-hidden={turned}
      sx={{
        position: "absolute",
        inset: 0,
        backfaceVisibility: "hidden",
        WebkitBackfaceVisibility: "hidden",
      }}
    >
      <Box
        sx={{
          position: "relative",
          width: "100%",
          height: "100%",
          bgcolor: "common.black",
          borderRadius: "6px",
          overflow: "hidden",
        }}
      >
        <Box
          ref={buttonRef}
          component="button"
          type="button"
          aria-label={`Show details for ${item.name}`}
          onClick={onTurn}
          sx={{
            display: "block",
            width: "100%",
            height: "100%",
            p: 0,
            border: 0,
            bgcolor: "transparent",
            cursor: "pointer",
            borderRadius: "6px",
            "&:focus-visible": { outlineOffset: "-3px" },
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
        </Box>
        {item.found_in_image.length > 0 && (
          <Box
            aria-label={foundLabel}
            sx={{
              position: "absolute",
              left: small ? 6 : 8,
              bottom: small ? 6 : 8,
              maxWidth: small ? "calc(100% - 12px)" : "calc(100% - 16px)",
              height: small ? 22 : 24,
              px: "8px",
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
              borderRadius: 12,
              bgcolor: "rgba(0, 0, 0, 0.62)",
              border: "1px solid rgba(255, 255, 255, 0.28)",
              color: "common.white",
              fontSize: small ? 11 : 11.5,
              fontWeight: 600,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
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
            buttonRef={expandRef}
            label={`View ${item.name} full size`}
            onClick={onExpand}
            size={small ? "compact" : "regular"}
          />
        )}
      </Box>
    </Box>
  );
}
