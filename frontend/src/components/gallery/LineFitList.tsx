import { Fragment, useLayoutEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";

interface Props {
  items: string[];
  maxLines?: number;
  keep: "first" | "last";
  pillLabel: (hidden: number) => string;
  earlier?: boolean;
}

function MeasuredLineFitList({
  items,
  maxLines = 2,
  keep,
  pillLabel,
  earlier = false,
}: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const lastWidth = useRef(0);
  const [shown, setShown] = useState(items.length);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || shown <= 1) return;
    const measuredLineHeight = Number.parseFloat(getComputedStyle(element).lineHeight) || 0;
    const lineHeight = Math.max(measuredLineHeight, 19);
    if (element.scrollHeight > lineHeight * maxLines + 1) {
      queueMicrotask(() => setShown((value) => Math.max(1, value - 1)));
    }
  }, [shown, items, maxLines]);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    lastWidth.current = element.getBoundingClientRect().width;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      if (Math.abs(width - lastWidth.current) > 0.5) {
        lastWidth.current = width;
        setShown(items.length);
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [items]);

  const hidden = items.length - shown;
  const visible =
    keep === "first" ? items.slice(0, shown) : items.slice(items.length - shown);
  const hiddenItems =
    keep === "first" ? items.slice(shown) : items.slice(0, hidden);
  const ariaLabel = earlier
    ? `and earlier: ${hiddenItems.join(", ")}`
    : `and ${hiddenItems.join(", ")}`;

  return (
    <Box component="span" ref={ref} sx={{ display: "block", lineHeight: 1.45 }}>
      {visible.map((item, index) => (
        <Fragment key={`${item}-${index}`}>
          {index > 0 && ", "}
          <Box component="span" sx={{ whiteSpace: "nowrap" }}>
            {item}
          </Box>
        </Fragment>
      ))}
      {hidden > 0 && (
        <Tooltip title={hiddenItems.join(", ")}>
          <Box
            component="span"
            aria-label={ariaLabel}
            sx={{
              display: "inline-block",
              ml: "6px",
              px: "6px",
              height: 18,
              lineHeight: "18px",
              borderRadius: "9px",
              bgcolor: (theme) =>
                theme.palette.mode === "dark" ? "#31343a" : "#ebe8e3",
              fontSize: 11,
              fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            {pillLabel(hidden)}
          </Box>
        </Tooltip>
      )}
    </Box>
  );
}

export default function LineFitList(props: Props) {
  const key = `${props.keep}:${props.maxLines ?? 2}:${props.items.join("\u0000")}`;
  return <MeasuredLineFitList key={key} {...props} />;
}
