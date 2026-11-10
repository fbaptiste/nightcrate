import { useEffect, useRef, useState, type RefObject } from "react";
import Box from "@mui/material/Box";
import type { GalleryItem } from "@/api/gallery";
import FlipTile from "@/components/common/FlipTile";
import NameWithAlternates from "@/components/common/NameWithAlternates";
import { cropSizeForView } from "@/lib/galleryRendition";
import { tileMinimums, useTrackWidth } from "@/lib/useTrackWidth";
import GalleryTileBack from "./GalleryTileBack";
import GalleryTileFront from "./GalleryTileFront";

type GridView = "small" | "medium" | "large";

interface Props {
  items: GalleryItem[];
  view: GridView;
  ws: string;
  resetKey: string;
  onExpand: (id: number) => void;
  expandRefs: RefObject<Map<number, HTMLButtonElement>>;
}

interface TileProps {
  item: GalleryItem;
  view: GridView;
  ws: string;
  trackWidth: number;
  turned: boolean;
  onTurn: (turned: boolean) => void;
  onExpand: () => void;
  expandRefs: RefObject<Map<number, HTMLButtonElement>>;
}

function GalleryGridTile({
  item,
  view,
  ws,
  trackWidth,
  turned,
  onTurn,
  onExpand,
  expandRefs,
}: TileProps) {
  const frontRef = useRef<HTMLButtonElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const expandRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const registered = expandRefs.current;
    const button = expandRef.current;
    if (button) registered.set(item.project_id, button);
    return () => {
      if (registered.get(item.project_id) === button) {
        registered.delete(item.project_id);
      }
    };
  }, [expandRefs, item.project_id]);

  const labelColor =
    item.status === "paused"
      ? (theme: { palette: { mode: string } }) =>
          theme.palette.mode === "dark" ? "#f0a35e" : "#b85500"
      : "text.secondary";
  let captionFontSize = 14;
  if (view === "small") captionFontSize = 13;
  if (view === "large") captionFontSize = 16;
  const statusLabel = item.status[0].toUpperCase() + item.status.slice(1);

  return (
    <Box sx={{ minWidth: 0 }}>
      <FlipTile
        turned={turned}
        onTurn={onTurn}
        frontButtonRef={frontRef}
        backButtonRef={backRef}
        front={
          <GalleryTileFront
            item={item}
            ws={ws}
            slotWidth={trackWidth}
            cropSize={cropSizeForView(view)}
            small={view === "small"}
            onTurn={() => onTurn(true)}
            onExpand={onExpand}
            buttonRef={frontRef}
            expandRef={expandRef}
          />
        }
        back={
          <GalleryTileBack
            item={item}
            view={view}
            turned={turned}
            onTurn={() => onTurn(false)}
            buttonRef={backRef}
          />
        }
      />
      <Box sx={{ pt: "8px" }}>
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            minWidth: 0,
            fontSize: captionFontSize,
            fontWeight: 600,
            whiteSpace: "nowrap",
          }}
        >
          <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>
            {item.name}
          </Box>
          {item.status !== "complete" && (
            <Box
              component="span"
              sx={{
                flex: "0 0 auto",
                px: "6px",
                border: "1px solid currentColor",
                borderRadius: "4px",
                color: labelColor,
                fontSize: 11,
                lineHeight: "16px",
                fontWeight: 600,
              }}
            >
              {statusLabel}
            </Box>
          )}
          {item.retired && (
            <Box
              component="span"
              sx={{
                flex: "0 0 auto",
                px: "6px",
                border: "1px solid currentColor",
                borderRadius: "4px",
                color: "text.secondary",
                fontSize: 11,
                lineHeight: "16px",
                fontWeight: 600,
              }}
            >
              Retired
            </Box>
          )}
        </Box>
        <Box
          sx={{
            color: "text.secondary",
            fontSize: view === "small" ? 12 : 13,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {item.targets.map((target, index) => (
            <NameWithAlternates
              key={target.dso_id}
              name={target.name}
              otherNames={target.also_known_as}
            >
              {index > 0 ? `, ${target.name}` : target.name}
            </NameWithAlternates>
          ))}
        </Box>
      </Box>
    </Box>
  );
}

export default function GalleryGrid({
  items,
  view,
  ws,
  resetKey,
  onExpand,
  expandRefs,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const trackWidth = useTrackWidth(view, containerRef);
  const [turned, setTurned] = useState<Set<number>>(new Set());

  useEffect(() => {
    queueMicrotask(() => setTurned(new Set()));
  }, [view, resetKey]);

  useEffect(() => {
    queueMicrotask(() => {
      setTurned((current) => {
        const surviving = [...current].filter((id) =>
          items.some((item) => item.project_id === id),
        );
        return new Set(surviving);
      });
    });
  }, [items]);

  const setItemTurned = (projectId: number, showBack: boolean) => {
    setTurned((current) => {
      const next = new Set(current);
      if (showBack) next.add(projectId);
      else next.delete(projectId);
      return next;
    });
  };

  return (
    <Box
      ref={containerRef}
      sx={{
        display: "grid",
        gridTemplateColumns: `repeat(auto-fill, minmax(${tileMinimums[view]}px, 1fr))`,
        columnGap: "16px",
        rowGap: view === "small" ? "20px" : "28px",
      }}
    >
      {items.map((item) => (
        <GalleryGridTile
          key={item.project_id}
          item={item}
          view={view}
          ws={ws}
          trackWidth={trackWidth}
          turned={turned.has(item.project_id)}
          onTurn={(showBack) => setItemTurned(item.project_id, showBack)}
          onExpand={() => onExpand(item.project_id)}
          expandRefs={expandRefs}
        />
      ))}
    </Box>
  );
}
