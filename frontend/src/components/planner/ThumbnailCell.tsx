/**
 * Thumbnail cell for the planner's target list + simulator background.
 *
 * Detects the backend's 1x1-pixel placeholder via ``naturalWidth`` and
 * polls with an exponential-ish backoff (fast first retry, slower
 * after) using a cache-busting query string until the real image
 * lands. A 204 (permanent fetch-error backoff) fires the <img>
 * onError handler; we swap to a neutral icon in that case.
 *
 * Supports all four variants (``list``, ``detail``, ``rig_framed``,
 * ``fov_simulator``). Rig-dependent variants accept ``fovMajor/MinorDeg``
 * props that flow into the URL. An optional ``aspectRatio`` prop lets
 * the rig-framed cell present a non-square bounding box that crops the
 * square 180×180 source via ``object-fit: cover`` to match the rig's
 * sensor proportions. ``fill`` mode makes the cell absolutely fill its
 * parent (used by FovSimulator as the background image).
 *
 * Also catches the "cached <img> race" — browsers can resolve the src
 * from HTTP cache synchronously between element creation and React
 * attaching the ``onLoad`` listener, dropping the load event. A
 * post-mount useLayoutEffect inspects ``img.complete`` and replays the
 * load logic when this happens, so revisits of a fully-cached grid
 * don't leave permanent spinners on top of rendered tiles.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import ImageOutlinedIcon from "@mui/icons-material/ImageOutlined";
import { thumbnailUrl, type ThumbnailVariant } from "@/api/planner";
import { useThumbnailCacheStore } from "@/stores/thumbnailCacheStore";

interface Props {
  dsoId: number;
  /** Pixel size when not in ``fill`` mode. Ignored when ``fill`` is true. */
  size?: number;
  variant?: ThumbnailVariant;
  fovMajorDeg?: number;
  fovMinorDeg?: number;
  /** Panned sky-region centre — only used by ``fov_simulator``. When
   *  both are set, the backend fetches DSS2 centred at (RA, Dec)
   *  rather than at the DSO's own coords. */
  centerRaDeg?: number;
  centerDecDeg?: number;
  /** Optional width:height ratio; defaults to 1 (square). When > 0, the
   *  cell renders a bounding box of ``size`` × ``size/aspectRatio`` with
   *  ``object-fit: cover`` so the stored square image crops to match. */
  aspectRatio?: number;
  /** When true, the cell positions itself absolutely inside its nearest
   *  positioned ancestor and fills it — used for the FOV simulator's
   *  background image. ``size`` is ignored for layout (but still used
   *  to compute the URL's variant parameters). */
  fill?: boolean;
  /** Fires once when the cell has loaded a real image (naturalWidth
   *  > 1). Re-fires if the request shape changes and a new real image
   *  lands. Callers use this to stage downstream work — e.g., the FOV
   *  simulator defers loading the tile ring until the centre tile is
   *  ready, so the backend's 4-slot HiPS semaphore focuses on the
   *  centre first. */
  onReady?: () => void;
  /** Long-poll window in milliseconds. When set (typical: 3000–4000
   *  for simulator tiles), the backend holds the request open for up
   *  to this long on a cache miss and returns the real image in the
   *  same round trip — shaves the ``CDS latency + next-poll cadence``
   *  overhead that pollers pay. Omit for list/detail thumbnails. */
  waitMs?: number;
}

const MAX_RETRIES = 30;

// Polling schedule (ms) — grows from a fast first poll to roughly
// CDS-fetch pacing. A warm backend cache lands the real image almost
// immediately, so the 400ms first retry keeps revisits feeling
// instant. Subsequent retries back off because a still-missing image
// means the CDS fetch is actually in flight and will take seconds
// more; no point hammering at 400 ms.
function retryDelayMs(attempt: number): number {
  if (attempt <= 1) return 400;
  if (attempt <= 3) return 900;
  if (attempt <= 6) return 1500;
  return 2500;
}

export default function ThumbnailCell({
  dsoId,
  size = 60,
  variant = "list",
  fovMajorDeg,
  fovMinorDeg,
  centerRaDeg,
  centerDecDeg,
  aspectRatio,
  fill = false,
  onReady,
  waitMs,
}: Props) {
  // ``version`` starts at 1 (never 0) so the URL always carries a
  // ``&__v=N`` cache-buster. Without it, ThumbnailCell's initial
  // request shares the base URL with FovSimulator's preload — and any
  // 202 placeholder the browser happened to cache under that base URL
  // (e.g., from a session before the endpoint's no-store headers
  // landed) would be served instead of a fresh request. Starting at 1
  // dodges the base-URL cache bucket entirely.
  const [version, setVersion] = useState(1);
  // Cache-generation counter from the backend. Bumps on cache clear so
  // browser HTTP caches can't serve pre-clear images. Subscribed via
  // the store so a generation change forces every ThumbnailCell to
  // re-render with the new URL suffix.
  const generation = useThumbnailCacheStore((s) => s.generation);
  const [failed, setFailed] = useState(false);
  // True while the most recently loaded <img> was the 1×1 placeholder —
  // i.e., we're waiting for the real image to land on a retry.
  const [loading, setLoading] = useState(true);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  // Idempotent — shared by the native ``load`` event and the
  // ``img.complete`` safety net. Repeat calls on a real image re-fire
  // setState no-ops; repeat calls on a placeholder short-circuit via
  // the in-flight ``retryTimerRef``.
  function handleImageResolved(img: HTMLImageElement): void {
    if (img.naturalWidth > 1 && img.naturalHeight > 1) {
      setLoading(false);
      onReady?.();
      return;
    }
    // Placeholder path — schedule a retry if one isn't pending.
    if (retryTimerRef.current != null) return;
    if (retryCountRef.current >= MAX_RETRIES) {
      setFailed(true);
      return;
    }
    retryCountRef.current += 1;
    retryTimerRef.current = setTimeout(() => {
      retryTimerRef.current = null;
      setVersion((v) => v + 1);
    }, retryDelayMs(retryCountRef.current));
  }

  useEffect(() => {
    // Reset retry state when the request shape changes (new DSO, new
    // variant, new rig). Also cancel any pending retry timer from the
    // previous request — otherwise it fires later and forces an
    // unnecessary refetch of the new one.
    retryCountRef.current = 0;
    if (retryTimerRef.current != null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    setVersion(1);
    setFailed(false);
    setLoading(true);
  }, [
    dsoId,
    variant,
    fovMajorDeg,
    fovMinorDeg,
    centerRaDeg,
    centerDecDeg,
    generation,
    waitMs,
  ]);

  // Cancel any pending retry when the cell unmounts (scroll past the
  // viewport, close the detail dialog, etc.) — otherwise 100 rows of
  // thumbnails stack up 100 unfired setTimeouts calling setState on
  // unmounted components.
  useEffect(() => {
    return () => {
      if (retryTimerRef.current != null) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
    };
  }, []);

  const src = `${thumbnailUrl(dsoId, variant, {
    fovMajorDeg,
    fovMinorDeg,
    centerRaDeg,
    centerDecDeg,
    generation,
    // Long-poll only on the very first attempt. Retries send
    // ``waitMs=0`` so a stuck CDS fetch can't stack up 4-second holds
    // across the polling schedule — otherwise a slow upstream turns
    // into 20+ seconds of held-open browser connections per tile.
    waitMs: version === 1 ? waitMs : 0,
  })}&__v=${version}`;

  // Cached ``<img>`` race: when ``src`` resolves from the browser HTTP
  // cache, the ``load`` event can fire synchronously at element
  // creation — before React attaches the onLoad listener — leaving
  // ``loading`` stuck true and the spinner overlaid on a fully-rendered
  // image. Checking ``img.complete`` after each ``src`` change catches
  // that case. ``handleImageResolved`` is idempotent so the parallel
  // path with the fired onLoad is harmless.
  useLayoutEffect(() => {
    const img = imgRef.current;
    if (img && img.complete && (img.naturalWidth > 0 || img.naturalHeight > 0)) {
      handleImageResolved(img);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  const renderWidth = fill ? "100%" : size;
  const renderHeight = fill
    ? "100%"
    : aspectRatio && aspectRatio > 0
      ? Math.round(size / aspectRatio)
      : size;

  const wrapperSx = {
    position: fill ? "absolute" : "relative",
    inset: fill ? 0 : "auto",
    width: fill ? "100%" : renderWidth,
    height: fill ? "100%" : renderHeight,
  } as const;

  if (failed) {
    return (
      <Box
        sx={{
          ...wrapperSx,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "text.disabled",
          bgcolor: "action.hover",
          borderRadius: fill ? 0 : 0.5,
        }}
      >
        <ImageOutlinedIcon fontSize="small" />
      </Box>
    );
  }

  return (
    <Box sx={wrapperSx}>
      <img
        ref={imgRef}
        onLoad={(e) => handleImageResolved(e.currentTarget)}
        onError={() => setFailed(true)}
        src={src}
        width={typeof renderWidth === "number" ? renderWidth : undefined}
        height={typeof renderHeight === "number" ? renderHeight : undefined}
        alt=""
        loading="lazy"
        style={{
          display: "block",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          borderRadius: fill ? 0 : 4,
          background: "rgba(0, 0, 0, 0.05)",
          userSelect: fill ? "none" : undefined,
          pointerEvents: fill ? "none" : undefined,
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
            // Dark scrim so the spinner reads on any background tint.
            bgcolor: "rgba(0, 0, 0, 0.18)",
            pointerEvents: "none",
            borderRadius: fill ? 0 : 0.5,
          }}
        >
          <CircularProgress size={fill ? 36 : 20} thickness={4} color="inherit" />
        </Box>
      )}
    </Box>
  );
}
