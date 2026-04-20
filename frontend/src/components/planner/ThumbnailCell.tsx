/**
 * Thumbnail cell for the planner's target list.
 *
 * Detects the backend's 1x1-pixel placeholder via ``naturalWidth`` and
 * retries every 2 seconds with a cache-busting query string until the
 * real image lands. A 204 (permanent fetch-error backoff) fires the
 * <img> onError handler; we swap to a neutral icon in that case.
 */
import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import ImageOutlinedIcon from "@mui/icons-material/ImageOutlined";
import { thumbnailUrl } from "@/api/planner";

interface Props {
  dsoId: number;
  size?: number;
  variant?: "list" | "detail";
}

const MAX_RETRIES = 30; // ~60 seconds at 2-second polling before we give up

export default function ThumbnailCell({
  dsoId,
  size = 60,
  variant = "list",
}: Props) {
  const [version, setVersion] = useState(0);
  const [failed, setFailed] = useState(false);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // Reset retry state when the DSO changes (e.g., user scrolls). Also
    // cancel any pending retry timer from the previous DSO — otherwise
    // it fires later and forces an unnecessary refetch of the new one.
    retryCountRef.current = 0;
    if (retryTimerRef.current != null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    setVersion(0);
    setFailed(false);
  }, [dsoId, variant]);

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

  if (failed) {
    return (
      <Box
        sx={{
          width: size,
          height: size,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "text.disabled",
          bgcolor: "action.hover",
          borderRadius: 0.5,
        }}
      >
        <ImageOutlinedIcon fontSize="small" />
      </Box>
    );
  }

  const src = `${thumbnailUrl(dsoId, variant)}${version ? `&__v=${version}` : ""}`;

  return (
    <img
      src={src}
      width={size}
      height={size}
      alt=""
      loading="lazy"
      style={{
        width: size,
        height: size,
        objectFit: "cover",
        borderRadius: 4,
        background: "rgba(0, 0, 0, 0.05)",
      }}
      onLoad={(e) => {
        const img = e.currentTarget;
        // The placeholder is a 1×1 PNG. Anything bigger is a real image.
        if (img.naturalWidth <= 1 || img.naturalHeight <= 1) {
          if (retryCountRef.current >= MAX_RETRIES) {
            setFailed(true);
            return;
          }
          retryCountRef.current += 1;
          if (retryTimerRef.current != null) clearTimeout(retryTimerRef.current);
          retryTimerRef.current = setTimeout(() => {
            retryTimerRef.current = null;
            setVersion((v) => v + 1);
          }, 2000);
        }
      }}
      onError={() => setFailed(true)}
    />
  );
}
