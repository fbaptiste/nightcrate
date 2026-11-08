import { useEffect, useRef, useState, type RefObject } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import { Link } from "react-router-dom";
import type { GalleryItem } from "@/api/gallery";
import { formatHoursMinutes } from "@/components/projects/IntegrationBars";
import { formatImagingRuns } from "@/lib/galleryRendition";
import LineFitList from "./LineFitList";
import RigSummary from "./RigSummary";
import StatusPills from "./StatusPills";

type GridView = "small" | "medium" | "large";

interface Props {
  item: GalleryItem;
  view: GridView;
  turned: boolean;
  onTurn: () => void;
  buttonRef: RefObject<HTMLButtonElement | null>;
}

interface BackContentProps {
  item: GalleryItem;
  runs: string[];
  large?: boolean;
}

function SmallBackContent({ item, runs }: BackContentProps) {
  const dateItems = runs.length ? runs : ["No imaging dates"];
  const nights = item.nights
    ? `${item.nights} ${item.nights === 1 ? "night" : "nights"}`
    : "";
  return (
    <Box sx={{ fontSize: 12, lineHeight: 1.45 }}>
      <LineFitList
        items={dateItems}
        keep="last"
        pillLabel={(hidden) => `+${hidden} earlier`}
        earlier
      />
      <Box sx={{ color: "text.secondary" }}>{nights}</Box>
      <Box sx={{ mt: "5px" }}>
        <RigSummary rigs={item.rigs} />
      </Box>
    </Box>
  );
}

function DetailBackContent({ item, runs, large = false }: BackContentProps) {
  const targetItems = item.targets.length
    ? item.targets.map((target) => target.name)
    : ["No targets"];
  const dateItems = runs.length ? runs : ["No imaging dates"];
  const integration = item.integration_minutes
    ? formatHoursMinutes(item.integration_minutes)
    : "None recorded";

  return (
    <Box
      component="dl"
      sx={{
        m: 0,
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        gap: large ? "6px 16px" : "4px 12px",
        fontSize: large ? 14 : 13,
        ...(large ? { mt: "14px" } : {}),
      }}
    >
      <Box component="dt" sx={{ color: "text.secondary" }}>
        Targets
      </Box>
      <Box component="dd" sx={{ m: 0, minWidth: 0 }}>
        <LineFitList
          items={targetItems}
          keep="first"
          pillLabel={(hidden) => `+${hidden}`}
        />
      </Box>
      <Box component="dt" sx={{ color: "text.secondary" }}>
        Imaging dates
      </Box>
      <Box component="dd" sx={{ m: 0, minWidth: 0 }}>
        <LineFitList
          items={dateItems}
          keep="last"
          pillLabel={(hidden) => `+${hidden} earlier`}
          earlier
        />
        {item.nights > 0 && (
          <Box sx={{ color: "text.secondary" }}>
            {item.nights} {item.nights === 1 ? "night" : "nights"}
          </Box>
        )}
      </Box>
      <Box component="dt" sx={{ color: "text.secondary" }}>
        Integration
      </Box>
      <Box
        component="dd"
        sx={{
          m: 0,
          color: item.integration_minutes ? "text.primary" : "text.secondary",
        }}
      >
        {integration}
      </Box>
      <Box component="dt" sx={{ color: "text.secondary" }}>
        Rigs
      </Box>
      <Box component="dd" sx={{ m: 0 }}>
        <RigSummary rigs={item.rigs} />
      </Box>
    </Box>
  );
}

export default function GalleryTileBack({
  item,
  view,
  turned,
  onTurn,
  buttonRef,
}: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [more, setMore] = useState(false);

  useEffect(() => {
    const body = bodyRef.current;
    if (!body) return;
    const check = () => {
      setMore(body.scrollTop + body.clientHeight < body.scrollHeight - 1);
    };
    check();
    const observer = new ResizeObserver(check);
    observer.observe(body);
    body.addEventListener("scroll", check);
    return () => {
      observer.disconnect();
      body.removeEventListener("scroll", check);
    };
  }, [item, view, turned]);

  const runs = formatImagingRuns(item);
  const small = view === "small";
  const large = view === "large";
  let padding = "12px 14px 10px";
  if (small) padding = "10px 10px 8px";
  if (large) padding = "20px 22px 16px";
  const fade = more
    ? { maskImage: "linear-gradient(to bottom, #000000 calc(100% - 28px), transparent)" }
    : {};

  return (
    <Box
      inert={!turned ? true : undefined}
      aria-hidden={!turned}
      onClick={(event) => {
        if (!(event.target as HTMLElement).closest("a")) onTurn();
      }}
      sx={{
        position: "absolute",
        inset: 0,
        transform: "rotateY(180deg)",
        backfaceVisibility: "hidden",
        WebkitBackfaceVisibility: "hidden",
        bgcolor: "background.paper",
        border: 1,
        borderColor: "divider",
        borderRadius: "6px",
        p: padding,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        cursor: "pointer",
      }}
    >
      <Box
        ref={buttonRef}
        component="button"
        type="button"
        aria-label={`Show image for ${item.name}`}
        onClick={onTurn}
        sx={{
          position: "absolute",
          inset: 0,
          p: 0,
          border: 0,
          bgcolor: "transparent",
          cursor: "pointer",
          borderRadius: "6px",
          "&:focus-visible": { outlineOffset: "-3px" },
        }}
      />
      <Box
        ref={bodyRef}
        sx={{
          position: "relative",
          zIndex: 1,
          flex: "1 1 auto",
          minHeight: 0,
          overflowY: "auto",
          scrollbarWidth: "none",
          "&::-webkit-scrollbar": { display: "none" },
          ...fade,
        }}
      >
        {!small && (
          <Box sx={{ display: "flex", justifyContent: "flex-end", mb: "4px" }}>
            <StatusPills status={item.status} retired={item.retired} />
          </Box>
        )}
        {small ? (
          <SmallBackContent item={item} runs={runs} />
        ) : (
          <DetailBackContent item={item} runs={runs} large={large} />
        )}
      </Box>
      <Box sx={{ position: "relative", zIndex: 2, flex: "none", pt: "8px" }}>
        <Button
          component={Link}
          to={`/projects/${item.project_id}`}
          variant="contained"
          size="small"
          onClick={(event) => event.stopPropagation()}
          sx={{
            minHeight: small ? 26 : 30,
            height: small ? 26 : 30,
            px: small ? 1 : 1.5,
            fontSize: small ? 12 : 13,
          }}
        >
          Open project
        </Button>
      </Box>
    </Box>
  );
}
