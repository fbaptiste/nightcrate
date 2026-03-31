import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { fetchHdus, fetchHeader } from "@/api/fits";
import { FitsHeaderTable } from "@/components/fits/FitsHeaderTable";
import { FitsImage } from "@/components/fits/FitsImage";
import { HduSelector } from "@/components/fits/HduSelector";

export function FitsViewerPage() {
  const [inputPath, setInputPath] = useState("");
  const [activePath, setActivePath] = useState("");
  const [selectedHdu, setSelectedHdu] = useState(0);
  const [tab, setTab] = useState(0);
  const [fitToWindow, setFitToWindow] = useState(true);

  const hdusQuery = useQuery({
    queryKey: ["hdus", activePath],
    queryFn: () => fetchHdus(activePath),
    enabled: activePath !== "",
  });

  const headerQuery = useQuery({
    queryKey: ["header", activePath, selectedHdu],
    queryFn: () => fetchHeader(activePath, selectedHdu),
    enabled: activePath !== "" && tab === 1,
  });

  function handleOpen() {
    setSelectedHdu(0);
    setTab(0);
    setActivePath(inputPath.trim());
  }

  const hdus = hdusQuery.data ?? [];
  const selectedHduInfo = hdus.find((h) => h.index === selectedHdu);
  const hasFile = activePath !== "";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Toolbar */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, p: 1.5, borderBottom: 1, borderColor: "divider", flexShrink: 0 }}>
        <TextField
          size="small"
          placeholder="Absolute path to .fits file…"
          value={inputPath}
          onChange={(e) => setInputPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleOpen()}
          inputProps={{ style: { fontFamily: "monospace", fontSize: "0.85rem" } }}
          sx={{ flexGrow: 1 }}
        />
        <Button variant="contained" onClick={handleOpen} disabled={!inputPath.trim()}>
          Open
        </Button>

        {hasFile && hdus.length > 0 && (
          <>
            <Divider orientation="vertical" flexItem />
            <HduSelector hdus={hdus} selected={selectedHdu} onChange={(i) => { setSelectedHdu(i); setTab(0); }} />
            <Button variant="outlined" size="small" onClick={() => setFitToWindow((v) => !v)}>
              {fitToWindow ? "1:1" : "Fit"}
            </Button>
          </>
        )}
      </Box>

      {/* Error */}
      {hdusQuery.isError && (
        <Alert severity="error" sx={{ mx: 2, mt: 1 }}>
          {String(hdusQuery.error)}
        </Alert>
      )}

      {/* Tabs + content */}
      {hasFile && !hdusQuery.isError && (
        <>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ px: 2, flexShrink: 0, borderBottom: 1, borderColor: "divider" }}>
            <Tab label="Image" disabled={!selectedHduInfo?.has_image} />
            <Tab label="Header" />
          </Tabs>

          <Box sx={{ flexGrow: 1, overflow: "hidden" }}>
            {tab === 0 && (
              selectedHduInfo?.has_image
                ? <FitsImage path={activePath} hdu={selectedHdu} fit={fitToWindow} />
                : <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
                    <Typography color="text.secondary">Selected HDU has no image data</Typography>
                  </Box>
            )}
            {tab === 1 && (
              headerQuery.isLoading
                ? <Typography sx={{ p: 2 }} color="text.secondary">Loading header…</Typography>
                : headerQuery.data
                  ? <FitsHeaderTable cards={headerQuery.data} />
                  : null
            )}
          </Box>
        </>
      )}

      {/* Empty state */}
      {!hasFile && (
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", flexGrow: 1 }}>
          <Typography color="text.secondary">Enter a path to a FITS file above and press Open</Typography>
        </Box>
      )}
    </Box>
  );
}
