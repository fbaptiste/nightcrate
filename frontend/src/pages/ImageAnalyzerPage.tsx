import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import ImageSearchIcon from "@mui/icons-material/ImageSearch";

import {
  fetchRecentFiles,
  isVirtualPath,
  recordRecentFile,
  type RecentFile,
} from "@/api/images";
import { setActivity } from "@/api/client";
import ImageAnalyzerView from "@/components/analyzer/ImageAnalyzerView";
import { FileBrowser } from "@/components/fits/FileBrowser";
import { monoFontFamily } from "@/theme/theme";

/**
 * The standalone Image Analyzer route.
 *
 * This page owns only the *file chooser* — Browse, the path field, Open, the
 * FileBrowser dialog, the empty state, Cmd+O, and the recent-files list.
 * Everything that operates on an already-chosen file lives in
 * `ImageAnalyzerView`, which the project overlay reuses.
 *
 * `recordRecentFile` deliberately stays here: recent files are a single global
 * list, so peeking at project frames in the overlay must not pollute it.
 */
export function ImageAnalyzerPage() {
  const { pathname } = useLocation();
  const [activePath, setActivePath] = useState("");
  const [inputPath, setInputPath] = useState("");
  const [displayName, setDisplayName] = useState<string | undefined>(undefined);
  const [browserOpen, setBrowserOpen] = useState(false);

  const recentQuery = useQuery({
    queryKey: ["recent-files"],
    queryFn: fetchRecentFiles,
  });
  const recentFiles: RecentFile[] = recentQuery.data ?? [];

  function openFile(path: string, name?: string) {
    setDisplayName(name);
    // Project/archive images show a readable label instead of the raw virtual path.
    if (isVirtualPath(path) && name) {
      setInputPath(`${path.split("::")[0]} / ${name}`);
    } else {
      setInputPath(path);
    }
    setActivePath(path);
    recordRecentFile(path).then(() => recentQuery.refetch());
  }

  function handleOpen() {
    // Don't re-open a virtual path — inputPath is a display string, not a path.
    if (isVirtualPath(activePath)) return;
    const p = inputPath.trim();
    if (p) openFile(p);
  }

  // Cmd/Ctrl+O opens this page's FileBrowser. Gated on the route because the
  // page stays mounted (hidden) while you're elsewhere — without the gate it
  // would portal a file browser over whatever you're actually looking at,
  // including the project analyzer overlay.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (pathname !== "/image-analyzer") return;
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if ((e.metaKey || e.ctrlKey) && e.key === "o") {
        e.preventDefault();
        setBrowserOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [pathname]);

  const toolbarStart = (
    <>
      <Button
        variant="outlined"
        size="small"
        onClick={() => setBrowserOpen(true)}
        startIcon={<FolderOpenIcon sx={{ fontSize: 16 }} />}
        sx={{ height: 32 }}
      >
        Browse
      </Button>
      <Autocomplete
        freeSolo
        forcePopupIcon
        clearOnBlur={false}
        blurOnSelect
        options={recentFiles}
        getOptionLabel={(opt) => (typeof opt === "string" ? opt : opt.name)}
        filterOptions={(options) => options}
        inputValue={inputPath}
        onInputChange={(_, value, reason) => {
          if (reason !== "reset") setInputPath(value);
        }}
        onChange={(_, value) => {
          if (value) {
            const path = typeof value === "string" ? value : value.path;
            const name =
              typeof value === "string"
                ? undefined
                : isVirtualPath(value.path)
                  ? value.name
                  : undefined;
            openFile(path, name);
          }
        }}
        sx={{ flexGrow: 1, "& .MuiInputBase-root": { height: 32 } }}
        slotProps={{ listbox: { style: { maxHeight: 320 } } }}
        renderInput={(params) => (
          <TextField
            {...params}
            size="small"
            placeholder="Path to image file…"
            onKeyDown={(e) => e.key === "Enter" && handleOpen()}
            inputProps={{
              ...params.inputProps,
              style: { fontFamily: monoFontFamily, fontSize: "0.75rem" },
            }}
          />
        )}
        renderOption={(props, option) => {
          const item =
            typeof option === "string" ? { path: option, name: option } : option;
          return (
            <li {...props} key={item.path}>
              <Typography sx={{ fontFamily: monoFontFamily, fontSize: "0.7rem" }}>
                {item.name}
              </Typography>
            </li>
          );
        }}
      />
      <Button
        variant="contained"
        size="small"
        onClick={handleOpen}
        disabled={
          !inputPath.trim() ||
          inputPath.trim() === activePath ||
          isVirtualPath(activePath)
        }
        sx={{ height: 32 }}
      >
        Open
      </Button>
    </>
  );

  const emptyState = (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexGrow: 1,
      }}
    >
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 2,
          maxWidth: 400,
        }}
      >
        <ImageSearchIcon sx={{ fontSize: 48, color: "text.secondary", opacity: 0.4 }} />
        <Typography variant="body1" color="text.secondary" textAlign="center">
          Open an image file to view it here
        </Typography>
        <Button
          variant="outlined"
          onClick={() => setBrowserOpen(true)}
          startIcon={<FolderOpenIcon />}
        >
          Browse Files
        </Button>
        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", justifyContent: "center" }}>
          {["FITS", "XISF", "PXI Project", "PNG", "JPEG", "TIFF"].map((fmt) => (
            <Chip
              key={fmt}
              label={fmt}
              size="small"
              variant="outlined"
              sx={{ fontSize: "0.7rem", height: 22 }}
            />
          ))}
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, opacity: 0.6 }}>
          {"⌘"}O / Ctrl+O to browse &nbsp;&bull;&nbsp; F to fit &nbsp;&bull;&nbsp; 1 for
          1:1
        </Typography>
      </Box>
    </Box>
  );

  return (
    <>
      <ImageAnalyzerView
        path={activePath}
        displayName={displayName}
        toolbarStart={toolbarStart}
        emptyState={emptyState}
      />
      <FileBrowser
        open={browserOpen}
        onClose={() => setBrowserOpen(false)}
        onSelect={(path, name) => {
          setActivity(`Open ${name || path.split("/").pop() || path}`);
          openFile(path, name);
        }}
        activePath={activePath}
      />
    </>
  );
}
