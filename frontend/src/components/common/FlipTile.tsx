import { useEffect, useRef, type ReactNode, type RefObject } from "react";
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
  const previousTurned = useRef(turned);
  useEffect(() => {
    if (previousTurned.current === turned) return;
    previousTurned.current = turned;
    const frame = requestAnimationFrame(() => {
      (turned ? backButtonRef : frontButtonRef).current?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [backButtonRef, frontButtonRef, turned]);

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
      >
        <Box
          inert={turned ? true : undefined}
          aria-hidden={turned}
          sx={{ position: "absolute", inset: 0, backfaceVisibility: "hidden", WebkitBackfaceVisibility: "hidden" }}
        >
          {front}
        </Box>
        <Box
          inert={!turned ? true : undefined}
          aria-hidden={!turned}
          sx={{ position: "absolute", inset: 0, transform: "rotateY(180deg)", backfaceVisibility: "hidden", WebkitBackfaceVisibility: "hidden" }}
        >
          {back}
        </Box>
      </Box>
    </Box>
  );
}
