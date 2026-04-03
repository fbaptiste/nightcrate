import { useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import FolderIcon from "@mui/icons-material/Folder";
import FolderZipIcon from "@mui/icons-material/FolderZip";
import ImageIcon from "@mui/icons-material/Image";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";
import LinkIcon from "@mui/icons-material/Link";
import StorageIcon from "@mui/icons-material/Storage";
import HomeIcon from "@mui/icons-material/Home";
import {
  browseArchive,
  browseDirectory,
  browseProject,
  fetchVolumes,
  type ArchiveBrowseResult,
  type BrowseResult,
  type ProjectBrowseResult,
  type VolumeEntry,
} from "@/api/files";
import { useSettingsStore } from "@/stores/settingsStore";

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (path: string, displayName?: string) => void;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileBrowser({ open, onClose, onSelect }: Props) {
  const { settings, update } = useSettingsStore();
  const initialPath = settings?.last_browse_path ?? "~";
  const favorites = settings?.browser_favorites ?? [];

  const [currentPath, setCurrentPath] = useState(initialPath);
  const [result, setResult] = useState<BrowseResult | null>(null);
  const [volumes, setVolumes] = useState<VolumeEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedDisplayName, setSelectedDisplayName] = useState<string | null>(null);

  // Project browsing state
  const [activeProject, setActiveProject] = useState<string | null>(null);
  const [projectResult, setProjectResult] = useState<ProjectBrowseResult | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);

  // Archive browsing state
  const [activeArchive, setActiveArchive] = useState<string | null>(null);
  const [archiveSubdir, setArchiveSubdir] = useState<string>("");
  const [archiveResult, setArchiveResult] = useState<ArchiveBrowseResult | null>(null);
  const [archiveLoading, setArchiveLoading] = useState(false);

  // Context menu state
  const [contextMenu, setContextMenu] = useState<{ mouseX: number; mouseY: number; folderName: string; folderPath: string } | null>(null);

  // Keep a ref to the latest settings so the browse effect can read it
  // without adding settings to its dependency array (which would loop).
  const settingsRef = useRef(settings);
  settingsRef.current = settings;

  // Sync initial path when settings load
  const initializedRef = useRef(false);
  useEffect(() => {
    if (settings?.last_browse_path && !initializedRef.current) {
      setCurrentPath(settings.last_browse_path);
      initializedRef.current = true;
    }
  }, [settings?.last_browse_path]);

  // Fetch volumes once when dialog opens
  useEffect(() => {
    if (!open) return;
    fetchVolumes().then(setVolumes).catch(() => {});
  }, [open]);

  // Fetch directory contents when path changes
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    setSelectedFile(null);
    browseDirectory(currentPath)
      .then((data) => {
        setResult(data);
        setLoading(false);
        // Persist last browsed path
        const s = settingsRef.current;
        if (s && data.path !== s.last_browse_path) {
          update({ last_browse_path: data.path });
        }
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  }, [currentPath, open]);

  // Fetch project contents when entering a project
  useEffect(() => {
    if (!activeProject) {
      setProjectResult(null);
      return;
    }
    setProjectLoading(true);
    setSelectedFile(null);
    browseProject(activeProject)
      .then((data) => {
        setProjectResult(data);
        setProjectLoading(false);
      })
      .catch((err) => {
        setError(String(err));
        setProjectLoading(false);
        setActiveProject(null);
      });
  }, [activeProject]);

  // Fetch archive contents when entering/navigating within an archive
  useEffect(() => {
    if (!activeArchive) {
      setArchiveResult(null);
      return;
    }
    setArchiveLoading(true);
    setSelectedFile(null);
    browseArchive(activeArchive, archiveSubdir)
      .then((data) => {
        setArchiveResult(data);
        setArchiveLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Failed to browse archive");
        setArchiveLoading(false);
        setActiveArchive(null);
      });
  }, [activeArchive, archiveSubdir]);

  function navigateTo(path: string) {
    setCurrentPath(path);
    setSelectedFile(null);
    setSelectedDisplayName(null);
    setActiveProject(null);
    setActiveArchive(null);
    setArchiveSubdir("");
    setArchiveResult(null);
  }

  function handleOpen() {
    if (selectedFile) {
      onSelect(selectedFile, selectedDisplayName ?? undefined);
      onClose();
    }
  }

  function handleFolderContextMenu(e: React.MouseEvent, folderName: string, folderPath: string) {
    e.preventDefault();
    setContextMenu({ mouseX: e.clientX, mouseY: e.clientY, folderName, folderPath });
  }

  function handleAddFavorite() {
    if (!contextMenu) return;
    const alreadyExists = favorites.some((f) => f.path === contextMenu.folderPath);
    if (!alreadyExists) {
      update({
        browser_favorites: [...favorites, { name: contextMenu.folderName, path: contextMenu.folderPath }],
      });
    }
    setContextMenu(null);
  }

  function handleRemoveFavorite(path: string) {
    update({ browser_favorites: favorites.filter((f) => f.path !== path) });
  }

  // Build breadcrumb segments from resolved path (handle both / and \ separators)
  const pathSegments = result?.path.split(/[/\\]/).filter(Boolean) ?? [];

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Open Image File</DialogTitle>
      <DialogContent
        sx={{ display: "flex", gap: 0, p: 0, minHeight: 450, overflow: "hidden" }}
      >
        {/* Volumes sidebar */}
        <Box
          sx={{
            width: 160,
            flexShrink: 0,
            borderRight: 1,
            borderColor: "divider",
            overflowY: "auto",
            bgcolor: "action.hover",
          }}
        >
          <List dense disablePadding>
            {volumes.map((vol) => (
              <ListItemButton
                key={vol.path}
                selected={result?.path.startsWith(vol.path) ?? false}
                onClick={() => navigateTo(vol.path)}
                sx={{ py: 0.75 }}
              >
                <ListItemIcon sx={{ minWidth: 28 }}>
                  {vol.name.startsWith("~") ? (
                    <HomeIcon fontSize="small" />
                  ) : (
                    <StorageIcon fontSize="small" />
                  )}
                </ListItemIcon>
                <ListItemText
                  primary={vol.name}
                  primaryTypographyProps={{ fontSize: "0.8rem", noWrap: true }}
                />
              </ListItemButton>
            ))}
          </List>
        </Box>

        <Divider orientation="vertical" flexItem />

        {/* Main file listing */}
        <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column", minWidth: 0, p: 1.5 }}>
          {/* Favorites pills */}
          {favorites.length > 0 && (
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, pb: 1 }}>
              {favorites.map((fav) => (
                <Tooltip key={fav.path} title={fav.path} arrow>
                  <Chip
                    label={fav.name}
                    size="small"
                    onClick={() => navigateTo(fav.path)}
                    onDelete={() => handleRemoveFavorite(fav.path)}
                    sx={{ fontSize: "0.75rem" }}
                  />
                </Tooltip>
              ))}
            </Box>
          )}

          {/* Breadcrumb navigation */}
          {result && (
            <Breadcrumbs sx={{ pb: 1, fontSize: "0.8rem", "& ol": { flexWrap: "wrap", rowGap: 0.5 }, "& li": { whiteSpace: "nowrap" } }}>
              <Link
                component="button"
                underline="hover"
                color="inherit"
                onClick={() => navigateTo("/")}
                sx={{ fontSize: "0.8rem" }}
              >
                /
              </Link>
              {pathSegments.map((seg, i) => {
                const segPath = "/" + pathSegments.slice(0, i + 1).join("/");
                const isLast = i === pathSegments.length - 1 && !activeProject && !activeArchive;
                return isLast ? (
                  <Typography key={segPath} color="text.primary" sx={{ fontSize: "0.8rem" }}>
                    {seg}
                  </Typography>
                ) : (
                  <Link
                    key={segPath}
                    component="button"
                    underline="hover"
                    color="inherit"
                    onClick={() => navigateTo(segPath)}
                    sx={{ fontSize: "0.8rem" }}
                  >
                    {seg}
                  </Link>
                );
              })}
              {activeProject && (
                <Typography color="text.primary" sx={{ fontSize: "0.8rem" }}>
                  {activeProject.split("/").pop()}
                </Typography>
              )}
              {activeArchive && (
                <>
                  <Chip
                    icon={<FolderZipIcon sx={{ fontSize: "0.85rem" }} />}
                    label={activeArchive.split("/").pop()}
                    size="small"
                    onClick={() => setArchiveSubdir("")}
                    sx={{ fontSize: "0.75rem", height: 20 }}
                  />
                  {archiveSubdir && archiveSubdir.split("/").filter(Boolean).map((seg, i, parts) => {
                    const subPath = parts.slice(0, i + 1).join("/");
                    const isLast = i === parts.length - 1;
                    return isLast ? (
                      <Typography key={subPath} color="text.primary" sx={{ fontSize: "0.8rem" }}>
                        {seg}
                      </Typography>
                    ) : (
                      <Link
                        key={subPath}
                        component="button"
                        underline="hover"
                        color="inherit"
                        onClick={() => setArchiveSubdir(subPath)}
                        sx={{ fontSize: "0.8rem" }}
                      >
                        {seg}
                      </Link>
                    );
                  })}
                </>
              )}
            </Breadcrumbs>
          )}

          {loading && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
              <CircularProgress size={28} />
            </Box>
          )}

          {error && (
            <Alert severity="warning" variant="outlined" sx={{ fontSize: "0.85rem" }}>{error}</Alert>
          )}

          {result && !loading && !activeProject && !activeArchive && (
            <List
              dense
              sx={{
                flexGrow: 1,
                overflow: "auto",
                border: 1,
                borderColor: "divider",
                borderRadius: 1,
              }}
            >
              {/* Parent directory */}
              {result.parent && (
                <ListItemButton onClick={() => navigateTo(result.parent!)}>
                  <ListItemIcon sx={{ minWidth: 36 }}>
                    <FolderIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText primary=".." primaryTypographyProps={{ fontSize: "0.85rem" }} />
                </ListItemButton>
              )}

              {/* Directories */}
              {result.dirs.map((dir) => (
                <ListItemButton
                  key={dir.path}
                  onClick={() => navigateTo(dir.path)}
                  onContextMenu={(e) => handleFolderContextMenu(e, dir.name, dir.path)}
                >
                  <ListItemIcon sx={{ minWidth: 36 }}>
                    <FolderIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText
                    primary={dir.name}
                    primaryTypographyProps={{ fontSize: "0.85rem" }}
                  />
                </ListItemButton>
              ))}

              {/* PixInsight projects */}
              {result.projects.map((proj) => (
                <ListItemButton
                  key={proj.path}
                  onClick={() => setActiveProject(proj.path)}
                >
                  <ListItemIcon sx={{ minWidth: 36 }}>
                    <AccountTreeIcon fontSize="small" color="primary" />
                  </ListItemIcon>
                  <ListItemText
                    primary={proj.name}
                    secondary="PixInsight Project"
                    primaryTypographyProps={{ fontSize: "0.85rem" }}
                    secondaryTypographyProps={{ fontSize: "0.7rem" }}
                  />
                </ListItemButton>
              ))}

              {/* Archives */}
              {result.archives?.map((archive) => (
                <ListItemButton
                  key={archive.path}
                  onClick={() => {
                    setActiveArchive(archive.path);
                    setArchiveSubdir("");
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 36 }}>
                    <FolderZipIcon fontSize="small" color="primary" />
                  </ListItemIcon>
                  <ListItemText
                    primary={archive.name}
                    secondary="Archive"
                    primaryTypographyProps={{ fontSize: "0.85rem" }}
                    secondaryTypographyProps={{ fontSize: "0.7rem" }}
                  />
                </ListItemButton>
              ))}

              {/* Image files */}
              {result.files.map((file) => (
                <ListItemButton
                  key={file.path}
                  selected={selectedFile === file.path}
                  onClick={() => { setSelectedFile(file.path); setSelectedDisplayName(null); }}
                  onDoubleClick={() => { onSelect(file.path); onClose(); }}
                >
                  <ListItemIcon sx={{ minWidth: 36 }}>
                    <InsertDriveFileIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText
                    primary={file.name}
                    secondary={formatSize(file.size)}
                    primaryTypographyProps={{
                      fontSize: "0.85rem",
                      fontFamily: "monospace",
                    }}
                    secondaryTypographyProps={{ fontSize: "0.75rem" }}
                  />
                </ListItemButton>
              ))}

              {/* Empty state */}
              {result.dirs.length === 0 && result.files.length === 0 && result.projects.length === 0 && (result.archives?.length ?? 0) === 0 && (
                <Typography sx={{ p: 2 }} color="text.secondary" variant="body2">
                  No directories or image files here
                </Typography>
              )}
            </List>
          )}

          {/* Project image listing */}
          {activeProject && !projectLoading && projectResult && (
            <List
              dense
              sx={{
                flexGrow: 1,
                overflow: "auto",
                border: 1,
                borderColor: "divider",
                borderRadius: 1,
              }}
            >
              {/* Back to directory */}
              <ListItemButton onClick={() => setActiveProject(null)}>
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <FolderIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary=".." primaryTypographyProps={{ fontSize: "0.85rem" }} />
              </ListItemButton>

              {projectResult.images.map((img) => {
                const virtualPath = `${activeProject}::${img.index}`;
                const meta = [img.filter, img.object, img.exposure ? `${img.exposure}s` : null]
                  .filter(Boolean)
                  .join(" · ");
                return (
                  <ListItemButton
                    key={img.index}
                    selected={selectedFile === virtualPath}
                    onClick={() => { setSelectedFile(virtualPath); setSelectedDisplayName(img.name); }}
                    onDoubleClick={() => { onSelect(virtualPath, img.name); onClose(); }}
                  >
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      {img.source === "referenced" ? (
                        <LinkIcon fontSize="small" />
                      ) : (
                        <ImageIcon fontSize="small" />
                      )}
                    </ListItemIcon>
                    <ListItemText
                      primary={img.name}
                      secondary={meta || (img.source === "referenced" ? "Referenced XISF" : "Embedded")}
                      primaryTypographyProps={{ fontSize: "0.85rem" }}
                      secondaryTypographyProps={{ fontSize: "0.7rem" }}
                    />
                    <Chip
                      label={img.source === "referenced" ? "ref" : "emb"}
                      size="small"
                      variant="outlined"
                      sx={{ fontSize: "0.65rem", height: 18, ml: 1 }}
                    />
                  </ListItemButton>
                );
              })}
            </List>
          )}

          {activeProject && projectLoading && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
              <CircularProgress size={28} />
            </Box>
          )}

          {/* Archive browse listing */}
          {activeArchive && !archiveLoading && archiveResult && (
            <List
              dense
              sx={{
                flexGrow: 1,
                overflow: "auto",
                border: 1,
                borderColor: "divider",
                borderRadius: 1,
              }}
            >
              {/* Back: go up within archive or exit archive */}
              <ListItemButton
                onClick={() => {
                  if (archiveResult.parent !== null) {
                    setArchiveSubdir(archiveResult.parent);
                  } else {
                    setActiveArchive(null);
                    setArchiveSubdir("");
                    setArchiveResult(null);
                  }
                }}
              >
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <FolderIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary=".." primaryTypographyProps={{ fontSize: "0.85rem" }} />
              </ListItemButton>

              {/* Archive directories */}
              {archiveResult.dirs.map((dir) => {
                const dirPath = archiveResult.subdir
                  ? `${archiveResult.subdir}/${dir.name}`
                  : dir.name;
                return (
                  <ListItemButton
                    key={dir.name}
                    onClick={() => setArchiveSubdir(dirPath)}
                  >
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      <FolderIcon fontSize="small" />
                    </ListItemIcon>
                    <ListItemText
                      primary={dir.name}
                      primaryTypographyProps={{ fontSize: "0.85rem" }}
                    />
                  </ListItemButton>
                );
              })}

              {/* Archive files */}
              {archiveResult.files.map((file) => {
                const entryPath = archiveResult.subdir
                  ? `${archiveResult.subdir}/${file.name}`
                  : file.name;
                const virtualPath = `${activeArchive}::${entryPath}`;
                const sizeLabel = file.size !== null
                  ? formatSize(file.size)
                  : undefined;
                return (
                  <ListItemButton
                    key={file.name}
                    selected={selectedFile === virtualPath}
                    onClick={() => {
                      setSelectedFile(virtualPath);
                      setSelectedDisplayName(file.name);
                    }}
                    onDoubleClick={() => {
                      onSelect(virtualPath, file.name);
                      onClose();
                    }}
                  >
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      <InsertDriveFileIcon fontSize="small" />
                    </ListItemIcon>
                    <ListItemText
                      primary={file.name}
                      secondary={sizeLabel}
                      primaryTypographyProps={{
                        fontSize: "0.85rem",
                        fontFamily: "monospace",
                      }}
                      secondaryTypographyProps={{ fontSize: "0.75rem" }}
                    />
                  </ListItemButton>
                );
              })}

              {/* Empty archive directory */}
              {archiveResult.dirs.length === 0 && archiveResult.files.length === 0 && (
                <Typography sx={{ p: 2 }} color="text.secondary" variant="body2">
                  No files in this archive directory
                </Typography>
              )}
            </List>
          )}

          {activeArchive && archiveLoading && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
              <CircularProgress size={28} />
            </Box>
          )}
        </Box>

        {/* Right-click context menu for folders */}
        <Menu
          open={contextMenu !== null}
          onClose={() => setContextMenu(null)}
          anchorReference="anchorPosition"
          anchorPosition={
            contextMenu ? { top: contextMenu.mouseY, left: contextMenu.mouseX } : undefined
          }
        >
          <MenuItem onClick={handleAddFavorite}>
            Add to favorites
          </MenuItem>
        </Menu>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleOpen} disabled={!selectedFile}>
          Open
        </Button>
      </DialogActions>
    </Dialog>
  );
}
