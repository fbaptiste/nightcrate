/**
 * One cell of the v0.18.0 sky-tile cache.
 *
 * Parallels ``ThumbnailCell`` in structure (retry on placeholder, backoff
 * schedule, cached-<img>-race safety net via ``imgRef +
 * useLayoutEffect([src])``) but targets the DSO-agnostic
 * ``/api/planner/sky-tile`` endpoint. The retry / loading machinery
 * keeps working across both the per-DSO thumbnail path and the
 * sky-region cell path; eventually the two will share a base
 * component, but today they evolve independently so the legacy path
 * can stay frozen.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import ImageOutlinedIcon from "@mui/icons-material/ImageOutlined";
import { skyTileUrl, type SkyTileCellLayout } from "@/api/planner";
import { useThumbnailCacheStore } from "@/stores/thumbnailCacheStore";

interface Props {
  /** Cell identity as returned by ``/api/planner/sky-tile-grid``. */
  cell: SkyTileCellLayout;
  /** CSS pixel width of the rendered ``<img>``. Typically the tier's
   *  native ``cell_width_px`` — the browser scales the source JPEG to
   *  whatever CSS size this is. */
  width: number;
  height: number;
  /** Long-poll window (ms) on the first request. Retries always
   *  send ``waitMs=0`` to avoid stacking connection holds against a
   *  slow CDS. */
  waitMs?: number;
  /** Fires once when a real image lands. The composite uses this to
   *  coordinate "first paint" signals, if needed. */
  onReady?: () => void;
  /** Browser-level hint for how urgently this image should load.
   *  Used by ``SkyTileComposite`` to bias Chrome/Edge/Safari toward
   *  loading rig-adjacent cells before far-out peripheral ones.
   *  Ignored on older browsers, which degrades to the default
   *  scheduler. */
  fetchPriority?: "high" | "low" | "auto";
}

const MAX_RETRIES = 30;

function retryDelayMs(attempt: number): number {
  if (attempt <= 1) return 400;
  if (attempt <= 3) return 900;
  if (attempt <= 6) return 1500;
  return 2500;
}

export default function SkyTileCell({
  cell,
  width,
  height,
  waitMs,
  onReady,
  fetchPriority,
}: Props) {
  const [version, setVersion] = useState(1);
  const generation = useThumbnailCacheStore((s) => s.generation);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  function markPermanentFailure(): void {
    setFailed(true);
    // Fire ``onReady`` on permanent failure too so a composite that
    // gates peripheral cells on the centre cell's first paint
    // (``SkyTileComposite``) doesn't get wedged when the centre
    // cell's CDS fetch fails — the rest of the grid still renders.
    onReady?.();
  }

  function handleImageResolved(img: HTMLImageElement): void {
    if (img.naturalWidth > 1 && img.naturalHeight > 1) {
      setLoading(false);
      onReady?.();
      return;
    }
    if (retryTimerRef.current != null) return;
    if (retryCountRef.current >= MAX_RETRIES) {
      markPermanentFailure();
      return;
    }
    retryCountRef.current += 1;
    retryTimerRef.current = setTimeout(() => {
      retryTimerRef.current = null;
      setVersion((v) => v + 1);
    }, retryDelayMs(retryCountRef.current));
  }

  // Reset on cell identity / generation change.
  useEffect(() => {
    retryCountRef.current = 0;
    if (retryTimerRef.current != null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    setVersion(1);
    setFailed(false);
    setLoading(true);
  }, [
    cell.nside,
    cell.ipix,
    cell.tier,
    cell.cell_i,
    cell.cell_j,
    generation,
    waitMs,
  ]);

  // Cancel pending retries on unmount.
  useEffect(() => {
    return () => {
      if (retryTimerRef.current != null) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
    };
  }, []);

  const src = `${skyTileUrl(cell, {
    generation,
    waitMs: version === 1 ? waitMs : 0,
  })}&__v=${version}`;

  // Cached-<img> race: when src resolves from the browser HTTP cache,
  // load can fire before React's onLoad listener attaches. Checking
  // img.complete after each src change catches that path.
  useLayoutEffect(() => {
    const img = imgRef.current;
    if (img && img.complete && (img.naturalWidth > 0 || img.naturalHeight > 0)) {
      handleImageResolved(img);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  if (failed) {
    return (
      <Box
        sx={{
          width,
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "text.disabled",
          bgcolor: "action.hover",
        }}
      >
        <ImageOutlinedIcon fontSize="small" />
      </Box>
    );
  }

  return (
    <Box sx={{ position: "relative", width, height }}>
      <img
        ref={imgRef}
        onLoad={(e) => handleImageResolved(e.currentTarget)}
        onError={markPermanentFailure}
        src={src}
        width={width}
        height={height}
        alt=""
        // Intentionally omit loading="lazy" for high-priority cells so
        // the browser doesn't defer them behind the viewport-intersect
        // heuristic; all our cells are expected to be in-viewport
        // shortly, and lazy delays the fetch on Safari.
        loading={fetchPriority === "high" ? "eager" : "lazy"}
        // ``fetchpriority`` is a DOM attribute with a lowercase name;
        // React 18.3+ accepts the camelCase prop and emits it
        // correctly. Browser support: Chrome/Edge ≥101, Safari ≥17.2,
        // Firefox ≥132. Unsupported browsers ignore it and fall back
        // to their default scheduler.
        fetchPriority={fetchPriority}
        style={{
          display: "block",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          background: "rgba(0, 0, 0, 0.05)",
          userSelect: "none",
          pointerEvents: "none",
        }}
      />
      {loading && (
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            bgcolor: "rgba(0, 0, 0, 0.18)",
            pointerEvents: "none",
          }}
        >
          <CircularProgress size={24} thickness={4} color="inherit" />
        </Box>
      )}
    </Box>
  );
}
