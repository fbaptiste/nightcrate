import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";

import { previewUrl } from "@/api/plateSolve";
import DsoAnnotationOverlay, { type OverlayDso } from "./DsoAnnotationOverlay";

interface Props {
  path?: string;
  hdu?: number;
  imageHref?: string;
  imgW?: number;
  imgH?: number;
  dsos?: OverlayDso[];
  selectedId?: number | null;
  onSelect?: (id: number) => void;
  mainIds?: Set<number>;
}

export default function ImagePreview({ path, hdu = 0, imageHref, imgW = 0, imgH = 0, dsos, selectedId = null, onSelect, mainIds }: Props) {
  const [retry, setRetry] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const src = imageHref ?? (path ? `${previewUrl(path, hdu, 1600)}&retry=${retry}` : "");
  const aspect = imgW > 0 && imgH > 0 ? `${imgW} / ${imgH}` : "16 / 9";
  return (
    <Box sx={{ position: "relative", bgcolor: "#05070b", borderRadius: "6px", overflow: "hidden", aspectRatio: aspect, width: "100%", display: "grid", placeItems: "center" }}>
      {dsos && imgW > 0 && imgH > 0 ? (
        <DsoAnnotationOverlay imageHref={src} imgW={imgW} imgH={imgH} dsos={dsos} selectedId={selectedId} onSelect={onSelect ?? (() => undefined)} mainIds={mainIds} />
      ) : (
        <Box component="img" key={`${src}-${retry}`} src={src} alt="Plate solve preview" onLoad={() => { setLoaded(true); setFailed(false); }} onError={() => { setFailed(true); setLoaded(false); }} sx={{ width: "100%", height: "100%", objectFit: "contain", display: loaded ? "block" : "none" }} />
      )}
      {!dsos && !loaded && !failed && <Typography color="text.secondary" sx={{ position: "absolute", fontSize: 13 }}>Loading preview…</Typography>}
      {!dsos && failed && <Button sx={{ position: "absolute", minHeight: 40 }} onClick={() => { setFailed(false); setRetry((value) => value + 1); }}>Retry preview</Button>}
    </Box>
  );
}
