import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";
import type { GallerySolveMarks } from "@/api/gallery";
import type { SlideshowSeconds } from "@/api/settings";
import { projectSolveImageUrl } from "@/api/projectSolve";
import { renderedImageUrl } from "@/api/projects";
import { useSettingsStore } from "@/stores/settingsStore";
import MatchChips from "./MatchChips";
import SlideshowBar from "./SlideshowBar";
import SolveMarkedImage from "./SolveMarkedImage";
import ViewerDetails, { type ViewerDetailsData } from "./ViewerDetails";
import { DEFAULT_SLIDESHOW_SECONDS, nextIndex } from "./slideshow";
import { useSlideshow } from "./useSlideshow";

export type ViewerSource =
  | { kind: "project"; imageId: number }
  | { kind: "solve"; solve: GallerySolveMarks };

export interface ViewerEntry {
  key: string;
  projectId: number;
  source: ViewerSource;
  fallbackImageId?: number | null;
  title: string;
  subtitle: string;
  matchMainTarget?: boolean;
  matchInImage?: boolean;
  details?: ViewerDetailsData;
}

interface Props {
  entries: ViewerEntry[];
  startKey: string | null;
  ws: string;
  onClose: (lastKey: string) => void;
  onSolveUnavailable?: (solveId: number) => void;
  solveRetries?: ReadonlyMap<number, number>;
}

const navSx = {
  position: "absolute",
  top: "50%",
  transform: "translateY(-50%)",
  width: 52,
  height: 52,
  color: "common.white",
  border: "1px solid rgba(255, 255, 255, 0.28)",
  bgcolor: "rgba(255, 255, 255, 0.08)",
  "&:hover": { bgcolor: "rgba(255, 255, 255, 0.18)" },
  "&.Mui-disabled": { color: "common.white", opacity: 0.25 },
} as const;

function sourceUrl(entry: ViewerEntry, ws: string): string {
  return entry.source.kind === "solve"
    ? projectSolveImageUrl(entry.projectId, "full", entry.source.solve.solve_id, ws)
    : renderedImageUrl(entry.projectId, entry.source.imageId, "full", ws);
}

function fadeSx(visible: boolean) {
  return {
    opacity: visible ? 1 : 0,
    pointerEvents: visible ? "auto" : "none",
    transition: "opacity 400ms ease",
    "@media (prefers-reduced-motion: reduce)": { transition: "none" },
  } as const;
}

export default function GalleryViewer({
  entries,
  startKey,
  ws,
  onClose,
  onSolveUnavailable,
  solveRetries = new Map(),
}: Props) {
  const savedSeconds = useSettingsStore((state) => state.settings?.gallery_slideshow_seconds);
  const updateSettings = useSettingsStore((state) => state.update);
  const [seconds, setSeconds] = useState<SlideshowSeconds>(savedSeconds ?? DEFAULT_SLIDESHOW_SECONDS);
  const intervalChangedRef = useRef(false);
  const adoptedSavedSecondsRef = useRef(savedSeconds != null);
  const [currentKey, setCurrentKey] = useState(startKey);
  const [failedSolveId, setFailedSolveId] = useState<number | null>(null);
  const [attemptGeneration, setAttemptGeneration] = useState(0);
  const [loadedGeneration, setLoadedGeneration] = useState<number | null>(null);
  const [failedGeneration, setFailedGeneration] = useState<number | null>(null);
  const [turned, setTurned] = useState(false);
  const turnedRef = useRef(false);
  const focusAfterTurnRef = useRef<"picture" | "details" | null>(null);
  const attemptGenerationRef = useRef(0);
  const attemptKeyRef = useRef("");
  const settledGenerationRef = useRef<number | null>(null);
  const failedSolveRetryRef = useRef(0);
  const lastIndexRef = useRef(0);
  const controlsHoveredRef = useRef(false);
  const controlsFocusedRef = useRef(false);
  const pointerStartRef = useRef<{ pointerId: number; x: number; y: number } | null>(null);
  const pictureAreaRef = useRef<HTMLDivElement>(null);
  const frontFaceRef = useRef<HTMLDivElement>(null);
  const backFaceRef = useRef<HTMLDivElement>(null);
  const showPictureButtonRef = useRef<HTMLButtonElement>(null);
  turnedRef.current = turned;

  const index = entries.findIndex((candidate) => candidate.key === currentKey);
  const entry = index >= 0 ? entries[index] : null;

  const advance = useCallback(() => {
    setCurrentKey((key) => {
      const at = entries.findIndex((candidate) => candidate.key === key);
      const next = nextIndex(at, 1, entries.length, true);
      return next == null ? key : entries[next].key;
    });
  }, [entries]);
  const applySeconds = useCallback((next: SlideshowSeconds) => {
    intervalChangedRef.current = true;
    setSeconds(next);
    void updateSettings({ gallery_slideshow_seconds: next });
  }, [updateSettings]);
  const slideshow = useSlideshow({
    count: entries.length,
    seconds,
    onAdvance: advance,
    onSecondsChange: applySeconds,
  });
  const {
    notePictureChanged,
    notePictureShown,
    pause,
    playing,
  } = slideshow;

  useEffect(() => {
    if (
      savedSeconds == null ||
      adoptedSavedSecondsRef.current ||
      intervalChangedRef.current
    ) return;
    adoptedSavedSecondsRef.current = true;
    setSeconds(savedSeconds);
  }, [savedSeconds]);

  useLayoutEffect(() => {
    if (index >= 0) lastIndexRef.current = index;
  }, [index]);

  const focusPictureAreaFrom = useCallback((face: HTMLDivElement | null) => {
    if (face?.contains(document.activeElement)) pictureAreaRef.current?.focus();
  }, []);

  const setPictureTurned = useCallback((next: boolean, forceFocus = false) => {
    if (next === turnedRef.current) {
      if (forceFocus) {
        if (next) showPictureButtonRef.current?.focus();
        else pictureAreaRef.current?.focus();
      }
      return;
    }
    const faceBeingHidden = next ? frontFaceRef.current : backFaceRef.current;
    focusAfterTurnRef.current = forceFocus || faceBeingHidden?.contains(document.activeElement)
      ? next ? "details" : "picture"
      : null;
    turnedRef.current = next;
    setTurned(next);
  }, []);

  useLayoutEffect(() => {
    const destination = focusAfterTurnRef.current;
    if (destination === "details" && turned) showPictureButtonRef.current?.focus();
    if (destination === "picture" && !turned) pictureAreaRef.current?.focus();
    focusAfterTurnRef.current = null;
  }, [turned]);

  useLayoutEffect(() => {
    focusPictureAreaFrom(backFaceRef.current);
    turnedRef.current = false;
    setTurned(false);
  }, [entry?.key, focusPictureAreaFrom]);

  useLayoutEffect(() => {
    if (!playing) return;
    focusPictureAreaFrom(backFaceRef.current);
    turnedRef.current = false;
    setTurned(false);
  }, [focusPictureAreaFrom, playing]);

  const retry = entry?.source.kind === "solve" ? solveRetries.get(entry.source.solve.solve_id) ?? 0 : 0;
  const solveFailed = Boolean(entry?.source.kind === "solve" && entry.source.solve.solve_id === failedSolveId);
  const projectSource = entry?.source.kind === "project"
    ? entry.source.imageId
    : solveFailed
      ? entry?.fallbackImageId
      : null;
  const projectSrc = entry && projectSource != null
    ? renderedImageUrl(entry.projectId, projectSource, "full", ws)
    : null;
  const attemptKey = entry
    ? `${entry.key}:${entry.source.kind}:${entry.source.kind === "solve" ? entry.source.solve.solve_id : entry.source.imageId}:${retry}:${solveFailed ? "fallback" : "primary"}:${projectSrc ?? "none"}`
    : "none";

  useLayoutEffect(() => {
    if (!entry || attemptKeyRef.current === attemptKey) return;
    attemptKeyRef.current = attemptKey;
    attemptGenerationRef.current += 1;
    settledGenerationRef.current = null;
    // A source attempt owns its readiness. Clear the previous attempt before paint.
    setAttemptGeneration(attemptGenerationRef.current);
    setLoadedGeneration(null);
    setFailedGeneration(null);
    notePictureChanged();
    if (solveFailed && !projectSrc) {
      settledGenerationRef.current = attemptGenerationRef.current;
      notePictureShown();
    }
  }, [attemptKey, entry, notePictureChanged, notePictureShown, projectSrc, solveFailed]);

  useEffect(() => {
    if (
      failedSolveId != null &&
      (solveRetries.get(failedSolveId) ?? 0) > failedSolveRetryRef.current
    ) {
      setFailedSolveId(null);
    }
  }, [failedSolveId, solveRetries]);

  useEffect(() => {
    if (currentKey == null || index >= 0) return;
    if (!playing) {
      onClose(currentKey);
      return;
    }
    if (entries.length === 0) {
      pause();
      onClose(currentKey);
      return;
    }
    setCurrentKey(entries[lastIndexRef.current % entries.length].key);
    if (entries.length === 1) pause();
  }, [currentKey, entries, index, onClose, pause, playing]);

  useEffect(() => {
    if (!entry) return;
    const previous = nextIndex(index, -1, entries.length, slideshow.playing);
    const next = nextIndex(index, 1, entries.length, slideshow.playing);
    for (const neighborIndex of new Set([previous, next])) {
      if (neighborIndex != null) new Image().src = sourceUrl(entries[neighborIndex], ws);
    }
  }, [entries, entry, index, slideshow.playing, ws]);

  if (startKey == null || !entry) return null;

  const attemptIsCurrent = (generation: number, key: string) =>
    generation === attemptGenerationRef.current && key === attemptKeyRef.current;
  const settle = (generation: number, key: string) => {
    if (!attemptIsCurrent(generation, key) || settledGenerationRef.current === generation) return;
    settledGenerationRef.current = generation;
    slideshow.notePictureShown();
  };
  const close = () => {
    slideshow.pause();
    onClose(entry.key);
  };
  const step = (delta: 1 | -1) => {
    const next = nextIndex(index, delta, entries.length, slideshow.playing);
    if (next == null) return;
    slideshow.notePictureChanged();
    setPictureTurned(false);
    setFailedSolveId(null);
    setCurrentKey(entries[next].key);
  };
  const handleKeyDown = (event: React.KeyboardEvent) => {
    slideshow.poke();
    if (event.key === " " || event.key === "Spacebar") {
      event.preventDefault();
      slideshow.toggle();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      slideshow.changeInterval(1);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      slideshow.changeInterval(-1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      step(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      step(1);
    } else if (event.key === "Enter" && event.target === pictureAreaRef.current && !slideshow.playing) {
      event.preventDefault();
      setPictureTurned(!turned, true);
    }
  };
  const handleKeyUp = (event: React.KeyboardEvent) => {
    if (event.key === " " || event.key === "Spacebar") event.preventDefault();
  };
  const controlsVisible = !slideshow.playing || slideshow.controlsVisible;
  const loaded = loadedGeneration === attemptGeneration;
  const failed = failedGeneration === attemptGeneration;
  const setControlsHovered = (hovered: boolean) => {
    controlsHoveredRef.current = hovered;
    slideshow.setHover(hovered || controlsFocusedRef.current);
  };
  const setControlsFocused = (focused: boolean) => {
    controlsFocusedRef.current = focused;
    slideshow.setHover(focused || controlsHoveredRef.current);
  };

  return (
    <Dialog
      open
      fullScreen
      onClose={(_event, reason) => {
        if (reason === "escapeKeyDown" && turned) {
          setPictureTurned(false, true);
          return;
        }
        close();
      }}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      // Pointer events, mouse only: after a tap, touch browsers send
      // imitation mouse events, and a mousemove handler would undo the
      // tap that just hid the controls.
      onPointerMove={(event) => { if (event.pointerType === "mouse") slideshow.poke(); }}
      PaperProps={{
        sx: {
          bgcolor: "#000000",
          backgroundImage: "none",
          color: "#e2e0dd",
          containerType: "size",
          containerName: "viewer",
          overflow: "hidden",
          cursor: controlsVisible ? "default" : "none",
          "@container viewer (max-width: 899px)": {
            "& .viewer-bottom": { gridTemplateColumns: "minmax(0, 1fr)", justifyItems: "center", gap: "10px" },
            "& .viewer-title": { justifySelf: "stretch", textAlign: "center" },
            "& .viewer-spacer": { display: "none" },
          },
          "@container viewer (max-width: 599px)": {
            "& .viewer-grid": { p: "60px 12px 16px" },
            "& .viewer-nav": { display: "none" },
            "& .viewer-bar": { justifySelf: "stretch", width: "100%", "& > *": { width: "100%", justifyContent: "space-between" } },
            "& .viewer-close": { top: 8, right: 8 },
          },
          "@container viewer (max-height: 499px)": {
            "& .viewer-grid": { p: "8px 76px 8px" },
            "& .viewer-bottom": { gridTemplateColumns: "minmax(0, 1fr) auto", justifyItems: "stretch", alignItems: "center", gap: "16px", pt: "8px" },
            "& .viewer-title": { textAlign: "left" },
            "& .viewer-nav": { width: 48, height: 48 },
            "& .viewer-prev": { left: 14 },
            "& .viewer-next": { right: 14 },
            "& .viewer-close": { top: 8, right: 14 },
          },
        },
      }}
    >
      <Box className="viewer-grid" sx={{ position: "absolute", inset: 0, display: "grid", gridTemplateRows: "minmax(0, 1fr) auto", p: "56px 88px 16px", bgcolor: "#000000" }}>
        <Box
          ref={pictureAreaRef}
          role={turned ? undefined : "button"}
          tabIndex={turned ? -1 : 0}
          aria-label={turned ? undefined : `Show details for ${entry.title}`}
          onPointerDown={(event) => {
            const interactive = (event.target as HTMLElement).closest("a, button, [role='button'], input");
            if (interactive && interactive !== event.currentTarget) return;
            event.currentTarget.setPointerCapture(event.pointerId);
            pointerStartRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
          }}
          onPointerUp={(event) => {
            const start = pointerStartRef.current;
            if (!start || start.pointerId !== event.pointerId) {
              pointerStartRef.current = null;
              return;
            }
            pointerStartRef.current = null;
            const interactive = (event.target as HTMLElement).closest("a, button, [role='button'], input");
            if (interactive && interactive !== event.currentTarget) return;
            const dx = event.clientX - start.x;
            const dy = event.clientY - start.y;
            if (Math.abs(dx) >= 50 && Math.abs(dx) > 1.5 * Math.abs(dy)) {
              step(dx < 0 ? 1 : -1);
              slideshow.poke();
            } else if (Math.abs(dx) < 10 && Math.abs(dy) < 10) {
              if (slideshow.playing && slideshow.controlsVisible) slideshow.hideNow();
              else if (slideshow.playing) slideshow.poke();
              else setPictureTurned(!turned, true);
            }
          }}
          onPointerCancel={() => { pointerStartRef.current = null; }}
          sx={{ position: "relative", minWidth: 0, minHeight: 0, overflow: "hidden", perspective: "1800px", touchAction: turned ? "pan-y" : "none", userSelect: "none", WebkitTouchCallout: "none", outline: "none", "&:focus-visible": { outline: "2px solid #e6b35e", outlineOffset: "2px" } }}
        >
          <Box sx={{ position: "absolute", inset: 0, transformStyle: "preserve-3d", transform: turned ? "rotateY(180deg)" : "none", transition: "transform 400ms cubic-bezier(0.3, 0.1, 0.2, 1)", "@media (prefers-reduced-motion: reduce)": { transition: "none" } }}>
          <Box
            ref={frontFaceRef}
            aria-hidden={turned}
            inert={turned ? true : undefined}
            sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", backfaceVisibility: "hidden", WebkitBackfaceVisibility: "hidden", cursor: slideshow.playing ? "default" : "pointer" }}
          >
          {!loaded && !failed && <CircularProgress sx={{ color: "#e2e0dd" }} />}
          {entry.source.kind === "solve" && !solveFailed ? (
            <Box sx={{ position: "absolute", inset: 0, opacity: loaded ? 1 : 0, transition: "opacity 300ms ease", "@media (prefers-reduced-motion: reduce)": { transition: "none" } }}>
              <SolveMarkedImage
                key={`${attemptKey}-${attemptGeneration}`}
                projectId={entry.projectId}
                solve={entry.source.solve}
                variant="full"
                ws={ws}
                alt={entry.title}
                matchMainTarget={entry.matchMainTarget}
                matchInImage={entry.matchInImage}
                onShown={() => {
                  const generation = attemptGeneration;
                  if (!attemptIsCurrent(generation, attemptKey)) return;
                  setLoadedGeneration(generation);
                  settle(generation, attemptKey);
                }}
                onUnavailable={() => {
                  const generation = attemptGeneration;
                  if (!attemptIsCurrent(generation, attemptKey)) return;
                  const solveId = entry.source.kind === "solve" ? entry.source.solve.solve_id : 0;
                  onSolveUnavailable?.(solveId);
                  failedSolveRetryRef.current = retry;
                  if (entry.fallbackImageId != null) setFailedSolveId(solveId);
                  else {
                    setFailedGeneration(generation);
                    setFailedSolveId(solveId);
                    settle(generation, attemptKey);
                  }
                }}
              />
            </Box>
          ) : failed || !projectSrc ? (
            <Box sx={{ color: "#e2e0dd" }}>Couldn't load the full-size image.</Box>
          ) : (
            <Box
              component="img"
              key={`${attemptKey}-${attemptGeneration}`}
              src={projectSrc}
              alt={entry.title}
              draggable={false}
              onDragStart={(event) => event.preventDefault()}
              onLoad={() => {
                const generation = attemptGeneration;
                if (!attemptIsCurrent(generation, attemptKey)) return;
                setLoadedGeneration(generation);
                settle(generation, attemptKey);
              }}
              onError={() => {
                const generation = attemptGeneration;
                if (!attemptIsCurrent(generation, attemptKey)) return;
                setFailedGeneration(generation);
                settle(generation, attemptKey);
              }}
              sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", minHeight: 0, objectFit: "contain", opacity: loaded ? 1 : 0, transition: "opacity 300ms ease", WebkitUserDrag: "none", WebkitTouchCallout: "none", "@media (prefers-reduced-motion: reduce)": { transition: "none" } }}
            />
          )}
          {(entry.source.kind !== "solve" || solveFailed) && <MatchChips mainTarget={entry.matchMainTarget ?? false} inImage={entry.matchInImage ?? false} compact={false} />}
          <Box aria-hidden={!slideshow.note} sx={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)", px: "20px", py: "12px", borderRadius: "12px", bgcolor: "rgba(0, 0, 0, 0.72)", border: "1px solid rgba(255, 255, 255, 0.20)", color: "#e2e0dd", fontSize: 18, fontWeight: 500, whiteSpace: "nowrap", pointerEvents: "none", opacity: slideshow.note ? 1 : 0, transition: "opacity 200ms ease", "@media (prefers-reduced-motion: reduce)": { transition: "none" } }}>
            {slideshow.note ?? ""}
          </Box>
          </Box>
          <Box
            ref={backFaceRef}
            role="group"
            aria-label={`Details for ${entry.title}`}
            aria-hidden={!turned}
            inert={!turned ? true : undefined}
            sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", transform: "rotateY(180deg)", backfaceVisibility: "hidden", WebkitBackfaceVisibility: "hidden", overflow: "hidden", touchAction: "pan-y", cursor: "pointer", py: "8px" }}
          >
            <Box sx={{ position: "relative", width: "min(600px, 100%)", maxHeight: "100%", overflowY: "auto", overscrollBehavior: "contain", touchAction: "pan-y", bgcolor: "#24272c", border: "1px solid rgba(255,255,255,0.14)", borderRadius: "12px", p: "24px 28px 22px", scrollbarWidth: "thin", "@container viewer (max-width: 599px)": { p: "18px 18px 16px" }, "@container viewer (max-height: 499px)": { p: "14px 18px" } }}>
              <Button
                ref={showPictureButtonRef}
                type="button"
                size="small"
                onClick={() => setPictureTurned(false, true)}
                sx={{ position: "absolute", top: 6, left: 8, zIndex: 4, minWidth: 0, px: "7px", py: "2px", color: "#e2e0dd", bgcolor: "rgba(0,0,0,0.72)", fontSize: 11, lineHeight: 1.4, textTransform: "none", opacity: 0, pointerEvents: "none", "&:focus-visible": { opacity: 1, pointerEvents: "auto", outline: "2px solid #e6b35e", outlineOffset: "2px" } }}
              >
                Show the picture
              </Button>
              <ViewerDetails projectId={entry.projectId} details={entry.details} active={turned} />
            </Box>
          </Box>
          </Box>
        </Box>
        <Box className="viewer-bottom" sx={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto minmax(0, 1fr)", alignItems: "end", gap: "24px", pt: "12px" }}>
          <Box className="viewer-title" sx={{ minWidth: 0, color: "#e2e0dd", fontSize: 14, ...fadeSx(controlsVisible) }}>
            <Box sx={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{entry.title}</Box>
            <Box sx={{ color: "#a3a09b", fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{entry.subtitle}</Box>
          </Box>
          <Box
            className="viewer-bar"
            onPointerEnter={(event) => { if (event.pointerType === "mouse") setControlsHovered(true); }}
            onPointerLeave={(event) => { if (event.pointerType === "mouse") setControlsHovered(false); }}
            onFocusCapture={(event) => setControlsFocused((event.target as HTMLElement).matches(":focus-visible"))}
            onBlurCapture={() => setControlsFocused(false)}
            sx={fadeSx(controlsVisible)}
          >
            <SlideshowBar playing={slideshow.playing} seconds={seconds} index={index} count={entries.length} onToggle={slideshow.toggle} onChangeInterval={slideshow.changeInterval} />
          </Box>
          <Box className="viewer-spacer" />
        </Box>
      </Box>
      <IconButton className="viewer-close" aria-label="Close" onClick={close} onPointerEnter={(event) => { if (event.pointerType === "mouse") setControlsHovered(true); }} onPointerLeave={(event) => { if (event.pointerType === "mouse") setControlsHovered(false); }} onFocus={(event) => setControlsFocused(event.currentTarget.matches(":focus-visible"))} onBlur={() => setControlsFocused(false)} sx={{ position: "absolute", top: 12, right: 16, width: 44, height: 44, color: "common.white", border: "1px solid rgba(255, 255, 255, 0.28)", bgcolor: "rgba(255, 255, 255, 0.08)", "&:hover": { bgcolor: "rgba(255, 255, 255, 0.18)" }, ...fadeSx(controlsVisible) }}><CloseIcon /></IconButton>
      <IconButton className="viewer-nav viewer-prev" aria-label="Previous image" disabled={nextIndex(index, -1, entries.length, slideshow.playing) == null} onClick={() => step(-1)} onPointerEnter={(event) => { if (event.pointerType === "mouse") setControlsHovered(true); }} onPointerLeave={(event) => { if (event.pointerType === "mouse") setControlsHovered(false); }} onFocus={(event) => setControlsFocused(event.currentTarget.matches(":focus-visible"))} onBlur={() => setControlsFocused(false)} sx={{ ...navSx, left: 20, ...fadeSx(controlsVisible), ...(!controlsVisible ? { opacity: "0 !important" } : {}) }}><ChevronLeftIcon sx={{ fontSize: 28 }} /></IconButton>
      <IconButton className="viewer-nav viewer-next" aria-label="Next image" disabled={nextIndex(index, 1, entries.length, slideshow.playing) == null} onClick={() => step(1)} onPointerEnter={(event) => { if (event.pointerType === "mouse") setControlsHovered(true); }} onPointerLeave={(event) => { if (event.pointerType === "mouse") setControlsHovered(false); }} onFocus={(event) => setControlsFocused(event.currentTarget.matches(":focus-visible"))} onBlur={() => setControlsFocused(false)} sx={{ ...navSx, right: 20, ...fadeSx(controlsVisible), ...(!controlsVisible ? { opacity: "0 !important" } : {}) }}><ChevronRightIcon sx={{ fontSize: 28 }} /></IconButton>
    </Dialog>
  );
}
