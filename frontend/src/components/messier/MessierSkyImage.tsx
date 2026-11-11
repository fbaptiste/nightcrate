import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import Box from "@mui/material/Box";
import { thumbnailUrl } from "@/api/planner";
import type { SurveyRequestQueue } from "@/lib/surveyRequestQueue";
import { useThumbnailCacheStore } from "@/stores/thumbnailCacheStore";

export type SurveyImageStatus = "loading" | "ready" | "failed";

interface Props {
  dsoId: number;
  ws: string;
  renderKey: string;
  rigId?: number;
  active: boolean;
  requestKey: number;
  messierNumber: number;
  scrollRootRef: RefObject<HTMLDivElement | null>;
  requestQueue: SurveyRequestQueue;
  alt: string;
  scale?: number;
  onStatusChange?: (status: SurveyImageStatus) => void;
}

export default function MessierSkyImage({
  dsoId,
  ws,
  renderKey,
  rigId,
  active,
  requestKey,
  messierNumber,
  scrollRootRef,
  requestQueue,
  alt,
  scale = 1,
  onStatusChange,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(false);
  const generation = useThumbnailCacheStore((state) => state.generation);
  const identityKey = `${dsoId}:${renderKey}:${ws}:${generation}`;
  const failedKeyRef = useRef<string | null>(null);
  const requestKeyRef = useRef(requestKey);
  const [retryCount, setRetryCount] = useState(0);
  const [loadStatus, setLoadStatus] = useState<{
    key: string;
    requestKey: number;
    status: SurveyImageStatus;
  }>({ key: "", requestKey: 0, status: "loading" });
  const [image, setImage] = useState<{
    key: string;
    src: string;
    ready: boolean;
  } | null>(null);
  const currentImage = image?.key === identityKey ? image : null;
  const src = currentImage?.src ?? null;
  const status = loadStatus.key === identityKey
    ? loadStatus.status === "ready" || loadStatus.requestKey === requestKey
      ? loadStatus.status
      : "loading"
    : "loading";

  useLayoutEffect(() => {
    requestKeyRef.current = requestKey;
  }, [requestKey]);

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

  useLayoutEffect(() => {
    onStatusChange?.(status);
  }, [onStatusChange, status]);

  useLayoutEffect(() => {
    return () => onStatusChange?.("loading");
  }, [identityKey, onStatusChange]);

  useEffect(() => {
    failedKeyRef.current = null;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setImage(null);
    });
    return () => {
      cancelled = true;
    };
  }, [identityKey]);

  useEffect(() => {
    if (failedKeyRef.current !== identityKey) return;
    queueMicrotask(() => {
      if (failedKeyRef.current !== identityKey) return;
      failedKeyRef.current = null;
      setLoadStatus({ key: identityKey, requestKey, status: "loading" });
      setRetryCount((current) => current + 1);
    });
  }, [identityKey, requestKey]);

  useEffect(() => {
    const objectUrl = image?.src;
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [image?.src]);

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
          rigId,
          generation,
          waitMs: first ? 0 : 4000,
        }),
        window.location.origin,
      );
      try {
        const result = await requestQueue.enqueue({
          messierNumber,
          initial: first,
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
            const response = await fetch(url, { signal });
            return {
              status: response.status,
              blob: response.status === 200 ? await response.blob() : null,
            };
          },
        });
        if (result.status === 200 && result.blob) {
          if (controller.signal.aborted) return;
          const objectUrl = URL.createObjectURL(result.blob);
          setImage({ key: identityKey, src: objectUrl, ready: false });
        } else if (result.status === 202 && Date.now() - started < 75_000) {
          timer = setTimeout(() => void poll(false), 1000);
        } else {
          failedKeyRef.current = identityKey;
          setLoadStatus({ key: identityKey, requestKey: requestKeyRef.current, status: "failed" });
        }
      } catch (error) {
        if ((error as DOMException).name !== "AbortError") {
          failedKeyRef.current = identityKey;
          setLoadStatus({ key: identityKey, requestKey: requestKeyRef.current, status: "failed" });
          setImage(null);
        }
      }
    };
    void poll(true);
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [active, dsoId, generation, identityKey, messierNumber, near, renderKey, requestQueue, retryCount, rigId, scrollRootRef, src, ws]);

  const handleLoad = () => {
    setLoadStatus({ key: identityKey, requestKey: requestKeyRef.current, status: "ready" });
    setImage((current) =>
      current?.key === identityKey && current.src === src
        ? { ...current, ready: true }
        : current,
    );
  };

  const handleError = () => {
    failedKeyRef.current = identityKey;
    setLoadStatus({ key: identityKey, requestKey: requestKeyRef.current, status: "failed" });
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
          <Box component="img" src={src} alt={alt} onLoad={handleLoad} onError={handleError} sx={{ display: "block", visibility: currentImage?.ready ? "visible" : "hidden", width: "100%", height: "100%", objectFit: "cover" }} />
        </Box>
      )}
    </Box>
  );
}
