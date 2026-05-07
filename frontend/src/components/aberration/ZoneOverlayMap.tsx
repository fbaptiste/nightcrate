import { useRef, useState, useEffect, useCallback } from "react";
import Box from "@mui/material/Box";
import { imageUrl, type StretchParams } from "@/api/images";
import type { SampleSquare, SampleGridResult } from "@/api/aberration";

interface Props {
  path: string;
  hdu: number;
  linked: StretchParams;
  grid: SampleGridResult;
  squares: SampleSquare[];
  selectedSquare: SampleSquare | null;
  onSquareClick: (sq: SampleSquare) => void;
  onSquareMoved: (sq: SampleSquare) => void;
}

export function ZoneOverlayMap({
  path, hdu, linked, grid, squares, selectedSquare, onSquareClick, onSquareMoved,
}: Props) {
  const src = imageUrl(path, hdu, linked);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    const update = () => {
      if (img.clientWidth > 0) setImgSize({ w: img.clientWidth, h: img.clientHeight });
    };
    img.addEventListener("load", update);
    const observer = new ResizeObserver(update);
    observer.observe(img);
    return () => { img.removeEventListener("load", update); observer.disconnect(); };
  }, []);

  // Image dimensions from grid layout
  const lastSq = squares[squares.length - 1];
  const imgW = lastSq ? Math.max(lastSq.x1, grid.square_size * grid.cols) : 1;
  const imgH = lastSq ? Math.max(lastSq.y1, grid.square_size * grid.rows) : 1;
  const scaleX = imgSize ? imgSize.w / imgW : 0;
  const scaleY = imgSize ? imgSize.h / imgH : 0;

  // Compute drag bounds per square: the midpoints between neighbors
  const computeBounds = useCallback((sq: SampleSquare) => {
    const sqSize = grid.square_size;
    const half = sqSize / 2;
    // Find neighbors
    const left = squares.find((s) => s.row === sq.row && s.col === sq.col - 1);
    const right = squares.find((s) => s.row === sq.row && s.col === sq.col + 1);
    const above = squares.find((s) => s.row === sq.row - 1 && s.col === sq.col);
    const below = squares.find((s) => s.row === sq.row + 1 && s.col === sq.col);

    // Center bounds: the square center must stay within these limits
    const minCx = left ? (left.x0 + left.x1 + sq.x0 + sq.x1) / 4 : half;
    const maxCx = right ? (right.x0 + right.x1 + sq.x0 + sq.x1) / 4 : imgW - half;
    const minCy = above ? (above.y0 + above.y1 + sq.y0 + sq.y1) / 4 : half;
    const maxCy = below ? (below.y0 + below.y1 + sq.y0 + sq.y1) / 4 : imgH - half;

    return { minCx, maxCx, minCy, maxCy };
  }, [squares, grid.square_size, imgW, imgH]);

  // Drag state
  const [dragging, setDragging] = useState<{
    sq: SampleSquare;
    startMouseX: number;
    startMouseY: number;
    startCx: number;
    startCy: number;
  } | null>(null);
  const [dragOffset, setDragOffset] = useState<{ row: number; col: number; dx: number; dy: number } | null>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent, sq: SampleSquare) => {
    e.preventDefault();
    e.stopPropagation();
    const cx = (sq.x0 + sq.x1) / 2;
    const cy = (sq.y0 + sq.y1) / 2;
    setDragging({ sq, startMouseX: e.clientX, startMouseY: e.clientY, startCx: cx, startCy: cy });
    setDragOffset(null);
  }, []);

  useEffect(() => {
    if (!dragging || !imgSize) return;

    const onMouseMove = (e: MouseEvent) => {
      const dxScreen = e.clientX - dragging.startMouseX;
      const dyScreen = e.clientY - dragging.startMouseY;
      // Convert screen delta to image coords
      const dxImg = dxScreen / scaleX;
      const dyImg = dyScreen / scaleY;

      const bounds = computeBounds(dragging.sq);
      const half = grid.square_size / 2;
      // New center, clamped to bounds
      const newCx = Math.max(bounds.minCx, Math.min(bounds.maxCx, dragging.startCx + dxImg));
      const newCy = Math.max(bounds.minCy, Math.min(bounds.maxCy, dragging.startCy + dyImg));
      // Clamp so square stays in image
      const clampedCx = Math.max(half, Math.min(imgW - half, newCx));
      const clampedCy = Math.max(half, Math.min(imgH - half, newCy));

      const origCx = (dragging.sq.x0 + dragging.sq.x1) / 2;
      const origCy = (dragging.sq.y0 + dragging.sq.y1) / 2;
      setDragOffset({
        row: dragging.sq.row,
        col: dragging.sq.col,
        dx: clampedCx - origCx,
        dy: clampedCy - origCy,
      });
    };

    const onMouseUp = () => {
      if (dragOffset) {
        const half = grid.square_size / 2;
        const origCx = (dragging.sq.x0 + dragging.sq.x1) / 2;
        const origCy = (dragging.sq.y0 + dragging.sq.y1) / 2;
        const newCx = origCx + dragOffset.dx;
        const newCy = origCy + dragOffset.dy;
        const newSq: SampleSquare = {
          ...dragging.sq,
          x0: Math.round(newCx - half),
          y0: Math.round(newCy - half),
          x1: Math.round(newCx + half),
          y1: Math.round(newCy + half),
        };
        onSquareMoved(newSq);
      }
      setDragging(null);
      setDragOffset(null);
    };

    const onTouchMove = (e: TouchEvent) => {
      if (e.touches.length !== 1) return;
      e.preventDefault();
      const ev = { clientX: e.touches[0].clientX, clientY: e.touches[0].clientY } as MouseEvent;
      onMouseMove(ev);
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("touchend", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onMouseUp);
    };
  }, [dragging, imgSize, scaleX, scaleY, computeBounds, grid.square_size, imgW, imgH, dragOffset, onSquareMoved]);

  return (
    <Box sx={{ position: "relative", height: "100%", display: "inline-block" }}>
      <Box
        component="img"
        ref={imgRef}
        src={src}
        draggable={false}
        sx={{ display: "block", height: "100%", width: "auto" }}
      />
      {/* Sample square markers — draggable */}
      {imgSize && squares.map((sq) => {
        const isSelected = selectedSquare?.row === sq.row && selectedSquare?.col === sq.col;
        const isDragging = dragging?.sq.row === sq.row && dragging?.sq.col === sq.col;

        // Apply drag offset if this square is being dragged
        let displayX0 = sq.x0;
        let displayY0 = sq.y0;
        if (dragOffset && dragOffset.row === sq.row && dragOffset.col === sq.col) {
          displayX0 += dragOffset.dx;
          displayY0 += dragOffset.dy;
        }

        const left = displayX0 * scaleX;
        const top = displayY0 * scaleY;
        const width = (sq.x1 - sq.x0) * scaleX;
        const height = (sq.y1 - sq.y0) * scaleY;

        return (
          <Box
            key={`${sq.row}-${sq.col}`}
            onMouseDown={(e) => handleMouseDown(e, sq)}
            onTouchStart={(e) => { if (e.touches.length === 1) { e.preventDefault(); e.stopPropagation(); const cx = (sq.x0 + sq.x1) / 2; const cy = (sq.y0 + sq.y1) / 2; setDragging({ sq, startMouseX: e.touches[0].clientX, startMouseY: e.touches[0].clientY, startCx: cx, startCy: cy }); setDragOffset(null); } }}
            onClick={(e) => { if (!dragOffset) { e.stopPropagation(); onSquareClick(sq); } }}
            sx={{
              position: "absolute",
              left,
              top,
              width,
              height,
              border: "1px solid",
              borderColor: isDragging ? "#ffffff" : isSelected ? "#ffffff" : sq.star_count > 0 ? "rgba(255,255,255,0.45)" : "rgba(255,255,255,0.15)",
              bgcolor: isDragging ? "rgba(255,255,255,0.25)" : isSelected ? "rgba(255,255,255,0.2)" : "transparent",
              cursor: isDragging ? "grabbing" : "grab",
              transition: isDragging ? "none" : "border-color 0.15s, background-color 0.15s",
              opacity: sq.star_count > 0 || isDragging ? 1 : 0.4,
              "&:hover": isDragging ? {} : {
                borderColor: "rgba(255,255,255,0.7)",
                bgcolor: "rgba(255,255,255,0.1)",
              },
            }}
          />
        );
      })}
    </Box>
  );
}
