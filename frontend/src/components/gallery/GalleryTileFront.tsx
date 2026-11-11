import type { RefObject } from "react";
import Box from "@mui/material/Box";
import type { GalleryItem } from "@/api/gallery";
import type { CropSize } from "@/api/projects";
import { pickRendition, tileImageUrl } from "@/lib/galleryRendition";
import ExpandButton from "./ExpandButton";
import GalleryImage from "./GalleryImage";
import MatchChips from "./MatchChips";
import SolveMarkedImage from "./SolveMarkedImage";

interface Props {
  item: GalleryItem;
  ws: string;
  slotWidth: number;
  cropSize: CropSize;
  small: boolean;
  onTurn: () => void;
  onExpand: () => void;
  buttonRef: RefObject<HTMLButtonElement | null>;
  expandRef: RefObject<HTMLButtonElement | null>;
  solveUnavailable: boolean;
  solveRetry: number;
  onSolveUnavailable: (solveId: number) => void;
}

export default function GalleryTileFront({
  item,
  ws,
  slotWidth,
  cropSize,
  small,
  onTurn,
  onExpand,
  buttonRef,
  expandRef,
  solveUnavailable,
  solveRetry,
  onSolveUnavailable,
}: Props) {
  const imageId = item.main_image_id;
  const solve = solveUnavailable ? null : item.solve;
  const src = tileImageUrl(
    item,
    cropSize,
    slotWidth,
    window.devicePixelRatio || 1,
    ws,
  );
  const canExpand = solve != null || imageId != null;

  return (
    <Box sx={{ width: "100%", height: "100%" }}>
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
          {solve ? (
            <SolveMarkedImage
              key={`${solve.solve_id}-${solveRetry}`}
              projectId={item.project_id}
              solve={solve}
              variant={pickRendition(slotWidth, window.devicePixelRatio || 1)}
              ws={ws}
              alt={item.name}
              onUnavailable={() => onSolveUnavailable(solve.solve_id)}
              matchMainTarget={item.match_main_target}
              matchInImage={item.match_in_image}
              compactChips={small}
            />
          ) : src ? (
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
        {!solve && (
          <MatchChips
            mainTarget={item.match_main_target}
            inImage={item.match_in_image}
            compact={small}
          />
        )}
        {canExpand && (
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
