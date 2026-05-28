import { useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddPhotoAlternateIcon from "@mui/icons-material/AddPhotoAlternate";
import CloseIcon from "@mui/icons-material/Close";
import StarIcon from "@mui/icons-material/Star";
import StarBorderIcon from "@mui/icons-material/StarBorder";
import { FileBrowser } from "@/components/fits/FileBrowser";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  horizontalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { ProjectImage } from "@/api/projects";
import { renderedImageUrl } from "@/api/projects";

const THUMB_SIZE = 80;

interface SortableThumbProps {
  projectId: number;
  image: ProjectImage;
  isViewed: boolean;
  isMain: boolean;
  onView: () => void;
  onSetMain: () => void;
  onRemove: () => void;
}

function SortableThumb({
  projectId,
  image,
  isViewed,
  isMain,
  onView,
  onSetMain,
  onRemove,
}: SortableThumbProps) {
  const [loaded, setLoaded] = useState(false);
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id: image.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <Box
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={onView}
      sx={{
        position: "relative",
        width: THUMB_SIZE,
        height: THUMB_SIZE,
        flexShrink: 0,
        borderRadius: 1,
        overflow: "hidden",
        cursor: "grab",
        border: 2,
        borderColor: isViewed ? "primary.main" : "divider",
        "&:hover .thumb-actions": { opacity: 1 },
      }}
    >
      {!loaded && (
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <CircularProgress size={20} />
        </Box>
      )}
      <Box
        component="img"
        src={renderedImageUrl(projectId, image.id, "thumb_sm")}
        alt=""
        onLoad={() => setLoaded(true)}
        sx={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          display: loaded ? "block" : "none",
        }}
        onError={(e) => {
          (e.target as HTMLImageElement).style.display = "none";
        }}
      />
      {isMain && (
        <StarIcon
          sx={{
            position: "absolute",
            top: 2,
            left: 2,
            fontSize: 16,
            color: "warning.main",
            filter: "drop-shadow(0 0 2px rgba(0,0,0,0.8))",
          }}
        />
      )}
      <Box
        className="thumb-actions"
        sx={{
          position: "absolute",
          top: 0,
          right: 0,
          opacity: 0,
          transition: "opacity 0.15s",
          display: "flex",
          gap: 0,
        }}
      >
        {!isMain && (
          <Tooltip title="Set as main image">
            <IconButton
              size="small"
              onClick={(e) => {
                e.stopPropagation();
                onSetMain();
              }}
              sx={{
                color: "white",
                bgcolor: "rgba(0,0,0,0.5)",
                "&:hover": { bgcolor: "rgba(0,0,0,0.7)" },
                p: 0.25,
              }}
            >
              <StarBorderIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title="Remove">
          <IconButton
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
            sx={{
              color: "white",
              bgcolor: "rgba(0,0,0,0.5)",
              "&:hover": { bgcolor: "rgba(0,0,0,0.7)" },
              p: 0.25,
            }}
          >
            <CloseIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>
      </Box>
    </Box>
  );
}

interface Props {
  projectId: number;
  images: ProjectImage[];
  viewedImageId: number | null;
  mainImageId: number | null;
  onViewImage: (id: number) => void;
  onSetMain: (imageId: number) => void;
  onRemove: (imageId: number) => void;
  onReorder: (imageIds: number[]) => void;
  onAddImages: (paths: string[]) => void;
  isAdding?: boolean;
}

export default function ImageGalleryStrip({
  projectId,
  images,
  viewedImageId,
  mainImageId,
  onViewImage,
  onSetMain,
  onRemove,
  onReorder,
  onAddImages,
  isAdding,
}: Props) {
  const [browserOpen, setBrowserOpen] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const ids = images.map((i) => i.id);
    const oldIndex = ids.indexOf(active.id as number);
    const newIndex = ids.indexOf(over.id as number);
    if (oldIndex === -1 || newIndex === -1) return;
    onReorder(arrayMove(ids, oldIndex, newIndex));
  };

  return (
    <>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          overflowX: "auto",
          py: 1,
          px: 0.5,
        }}
      >
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={images.map((i) => i.id)}
            strategy={horizontalListSortingStrategy}
          >
            {images.map((img) => (
              <SortableThumb
                key={img.id}
                projectId={projectId}
                image={img}
                isViewed={img.id === viewedImageId}
                isMain={img.id === mainImageId}
                onView={() => onViewImage(img.id)}
                onSetMain={() => onSetMain(img.id)}
                onRemove={() => onRemove(img.id)}
              />
            ))}
          </SortableContext>
        </DndContext>

        {isAdding ? (
          <Box
            sx={{
              width: THUMB_SIZE,
              height: THUMB_SIZE,
              flexShrink: 0,
              borderRadius: 1,
              border: 2,
              borderColor: "divider",
              borderStyle: "dashed",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <CircularProgress size={24} />
          </Box>
        ) : (
          <Tooltip title="Add images">
            <IconButton
              onClick={() => setBrowserOpen(true)}
              sx={{
                width: THUMB_SIZE,
                height: THUMB_SIZE,
                flexShrink: 0,
                borderRadius: 1,
                border: 2,
                borderColor: "divider",
                borderStyle: "dashed",
              }}
            >
              <AddPhotoAlternateIcon />
            </IconButton>
          </Tooltip>
        )}

        {images.length === 0 && !isAdding && (
          <Typography variant="body2" color="text.secondary" sx={{ ml: 1 }}>
            No images yet. Click + to add.
          </Typography>
        )}
      </Box>

      <FileBrowser
        open={browserOpen}
        onClose={() => setBrowserOpen(false)}
        onSelect={(path) => {
          setBrowserOpen(false);
          onAddImages([path]);
        }}
        title="Add Image to Project"
        emptyMessage="No image files in this directory"
      />
    </>
  );
}
