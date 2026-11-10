import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import Box from "@mui/material/Box";
import { thumbnailUrl } from "@/api/planner";
import type { SurveyRequestQueue } from "@/lib/surveyRequestQueue";

interface Props {
  dsoId: number;
  ws: string;
  renderKey: string;
  active: boolean;
  requestKey: number;
  messierNumber: number;
  scrollRootRef: RefObject<HTMLDivElement | null>;
  requestQueue: SurveyRequestQueue;
  alt: string;
  scale?: number;
  onReadyChange?: (ready: boolean) => void;
}

export default function MessierSkyImage({
  dsoId,
  ws,
  renderKey,
  active,
  requestKey,
  messierNumber,
  scrollRootRef,
  requestQueue,
  alt,
  scale = 1,
  onReadyChange,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(false);
  const identityKey = `${dsoId}:${renderKey}:${ws}`;
  const objectUrlRef = useRef<string | null>(null);
  const failedKeyRef = useRef<string | null>(null);
  const [image, setImage] = useState<{
    key: string;
    src: string;
    ready: boolean;
  } | null>(null);
  const currentImage = image?.key === identityKey ? image : null;
  const src = currentImage?.src ?? null;

  useEffect(() => {
    const host = hostRef.current;
    const root = scrollRootRef.current;
    if (!host || !root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        setNear(entries.some((entry) => entry.isIntersecting));
      },
      { root, rootMargin: "400px" },
    );
    observer.observe(host);
    return () => observer.disconnect();
  }, [scrollRootRef]);

  useEffect(() => {
    onReadyChange?.(currentImage?.ready ?? false);
  }, [currentImage?.ready, onReadyChange]);

  useLayoutEffect(() => {
    onReadyChange?.(false);
    return () => onReadyChange?.(false);
  }, [identityKey, onReadyChange]);

  useEffect(() => {
    failedKeyRef.current = null;
    return () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    };
  }, [identityKey]);

  useEffect(() => {
    if (failedKeyRef.current === identityKey) failedKeyRef.current = null;
  }, [identityKey, requestKey]);

  useEffect(() => {
    if (!active) return;
    if (!near || src || failedKeyRef.current === identityKey) return;
    const controller = new AbortController();
    const started = Date.now();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async (first: boolean) => {
      const url = new URL(
        thumbnailUrl(dsoId, "checklist", {
          ws,
          renderKey,
          waitMs: first ? 4000 : 0,
        }),
        window.location.origin,
      );
      url.searchParams.set("_poll", String(Date.now()));
      try {
        const result = await requestQueue.enqueue({
          messierNumber,
          signal: controller.signal,
          distance: () => {
            const host = hostRef.current;
            const root = scrollRootRef.current;
            if (!host || !root) return Number.POSITIVE_INFINITY;
            const hostRect = host.getBoundingClientRect();
            const rootRect = root.getBoundingClientRect();
            if (hostRect.bottom < rootRect.top) return rootRect.top - hostRect.bottom;
            if (hostRect.top > rootRect.bottom) return hostRect.top - rootRect.bottom;
            return 0;
          },
          run: async (signal) => {
            const response = await fetch(url, { cache: "no-store", signal });
            return {
              status: response.status,
              blob: response.status === 200 ? await response.blob() : null,
            };
          },
        });
        if (result.status === 200 && result.blob) {
          if (controller.signal.aborted) return;
          const objectUrl = URL.createObjectURL(result.blob);
          objectUrlRef.current = objectUrl;
          setImage({ key: identityKey, src: objectUrl, ready: false });
        } else if (result.status === 202 && Date.now() - started < 75_000) {
          timer = setTimeout(() => void poll(false), 2500);
        }
      } catch (error) {
        if ((error as DOMException).name !== "AbortError") {
          failedKeyRef.current = identityKey;
          setImage(null);
        }
      }
    };
    void poll(true);
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [active, dsoId, identityKey, messierNumber, near, renderKey, requestKey, requestQueue, scrollRootRef, src, ws]);

  const handleLoad = () => {
    setImage((current) =>
      current?.key === identityKey && current.src === src
        ? { ...current, ready: true }
        : current,
    );
  };

  const handleError = () => {
    failedKeyRef.current = identityKey;
    onReadyChange?.(false);
    if (src) URL.revokeObjectURL(src);
    if (objectUrlRef.current === src) objectUrlRef.current = null;
    setImage((current) =>
      current?.key === identityKey && current.src === src ? null : current,
    );
  };

  return (
    <Box ref={hostRef} sx={{ position: "absolute", inset: 0 }}>
      {src && (
        <Box
          sx={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: `${100 / scale}%`,
            height: `${100 / scale}%`,
            transform: "translate(-50%, -50%)",
          }}
        >
          <Box component="img" src={src} alt={alt} onLoad={handleLoad} onError={handleError} sx={{ display: "block", width: "100%", height: "100%", objectFit: "cover" }} />
        </Box>
      )}
    </Box>
  );
}
