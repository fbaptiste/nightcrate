import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import Box from "@mui/material/Box";

interface Props {
  turned: boolean;
  onTurn: (next: boolean) => void;
  front: ReactNode;
  back: ReactNode;
  frontButtonRef: RefObject<HTMLButtonElement | null>;
  backButtonRef: RefObject<HTMLButtonElement | null>;
}

export default function FlipTile({
  turned,
  onTurn,
  front,
  back,
  frontButtonRef,
  backButtonRef,
}: Props) {
  const [settled, setSettled] = useState(true);
  const [previousSettledTurned, setPreviousSettledTurned] = useState(turned);
  const previousTurned = useRef(turned);
  const timerTurned = useRef(turned);
  const settleTimer = useRef<number | null>(null);

  if (previousSettledTurned !== turned) {
    setPreviousSettledTurned(turned);
    const reducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    setSettled(Boolean(reducedMotion));
  }

  useEffect(() => {
    if (previousTurned.current === turned) return;
    previousTurned.current = turned;
    const frame = requestAnimationFrame(() => {
      (turned ? backButtonRef : frontButtonRef).current?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [backButtonRef, frontButtonRef, turned]);

  useEffect(() => {
    if (timerTurned.current === turned) return;
    timerTurned.current = turned;
    const reducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion) return;

    settleTimer.current = window.setTimeout(() => {
      settleTimer.current = null;
      setSettled(true);
    }, 450);
    return () => {
      if (settleTimer.current !== null) {
        window.clearTimeout(settleTimer.current);
        settleTimer.current = null;
      }
    };
  }, [turned]);

  return (
    <Box
      onKeyDown={(event) => {
        if (event.key === "Escape" && turned) onTurn(false);
      }}
      sx={{ perspective: "1400px" }}
    >
      <Box
        sx={{
          position: "relative",
          width: "100%",
          aspectRatio: "4 / 3",
          transformStyle: "preserve-3d",
          transform: turned ? "rotateY(180deg)" : "none",
          transition: "transform 400ms cubic-bezier(0.3, 0.1, 0.2, 1)",
          "@media (prefers-reduced-motion: reduce)": { transition: "none" },
        }}
        onTransitionEnd={(event) => {
          if (
            event.propertyName === "transform" &&
            event.target === event.currentTarget
          ) {
            if (settleTimer.current !== null) {
              window.clearTimeout(settleTimer.current);
              settleTimer.current = null;
            }
            setSettled(true);
          }
        }}
      >
        <Box
          inert={turned ? true : undefined}
          aria-hidden={turned}
          sx={{ position: "absolute", inset: 0, visibility: turned && settled ? "hidden" : "visible", transition: "visibility 0s", backfaceVisibility: "hidden", WebkitBackfaceVisibility: "hidden" }}
        >
          {front}
        </Box>
        <Box
          inert={!turned ? true : undefined}
          aria-hidden={!turned}
          sx={{ position: "absolute", inset: 0, transform: "rotateY(180deg)", visibility: !turned && settled ? "hidden" : "visible", transition: "visibility 0s", backfaceVisibility: "hidden", WebkitBackfaceVisibility: "hidden" }}
        >
          {back}
        </Box>
      </Box>
    </Box>
  );
}
