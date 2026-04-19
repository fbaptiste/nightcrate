import { useState, useEffect } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CreateNewFolderIcon from "@mui/icons-material/CreateNewFolder";
import DescriptionIcon from "@mui/icons-material/Description";
import FolderIcon from "@mui/icons-material/Folder";
import HomeIcon from "@mui/icons-material/Home";
import StorageIcon from "@mui/icons-material/Storage";
import { useQuery } from "@tanstack/react-query";
import {
  fetchAdminInfo,
  fetchAdminStatus,
  setupDatabase,
  activateDatabase,
  browseForDatabase,
  fetchShortcuts,
  createFolder,
} from "@/api/admin";

/** Convert a database name to a filename slug (e.g., "Fred's Rig" → "freds_rig.db") */
function nameToFilename(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return slug ? `${slug}.db` : "nightcrate.db";
}

export function SetupWizard() {
  const [name, setName] = useState("My NightCrate Database");
  const [directory, setDirectory] = useState("");
  const [browseOpen, setBrowseOpen] = useState(false);
  const [browsePath, setBrowsePath] = useState("~");
  const [newFolderName, setNewFolderName] = useState("");
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data: info } = useQuery({
    queryKey: ["adminInfo"],
    queryFn: fetchAdminInfo,
  });

  const { data: status } = useQuery({
    queryKey: ["adminStatus"],
    queryFn: fetchAdminStatus,
  });

  const { data: shortcuts } = useQuery({
    queryKey: ["admin-shortcuts"],
    queryFn: fetchShortcuts,
  });

  const {
    data: browseResult,
    isLoading: browseLoading,
    refetch: refetchBrowse,
  } = useQuery({
    queryKey: ["admin-browse", browsePath],
    queryFn: () => browseForDatabase(browsePath),
    enabled: browseOpen,
  });

  useEffect(() => {
    if (info && !directory) {
      setDirectory(info.app_data_dir);
    }
  }, [info, directory]);

  const fullPath = directory
    ? `${directory.replace(/\/$/, "")}/${nameToFilename(name)}`
    : "";

  const knownDbs = status?.known_databases ?? [];
  const availableDbs = knownDbs.filter((db) => db.available);
  const unavailableDbs = knownDbs.filter((db) => !db.available);
  const hasKnownDbs = knownDbs.length > 0;
  const hasAvailableDbs = availableDbs.length > 0;

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await setupDatabase({ path: fullPath, name });
      window.location.reload();
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Failed to create database.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleActivateExisting = async (path: string) => {
    setSubmitting(true);
    try {
      await activateDatabase(path);
      window.location.reload();
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Failed to activate database.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleBrowseSelect = (dirPath: string) => {
    setDirectory(dirPath);
    setBrowseOpen(false);
  };

  const handleBrowseNavigate = (dirPath: string) => {
    setBrowsePath(dirPath);
  };

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return;
    const currentPath = browseResult?.path ?? browsePath;
    const newPath = `${currentPath.replace(/\/$/, "")}/${newFolderName.trim()}`;
    try {
      const result = await createFolder(newPath);
      setNewFolderOpen(false);
      setNewFolderName("");
      handleBrowseNavigate(result.path);
      void refetchBrowse();
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Failed to create folder.",
      );
    }
  };

  return (
    <Box
      sx={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        height: "100vh",
        bgcolor: "background.default",
      }}
    >
      <Card sx={{ maxWidth: 600, width: "100%", mx: 2 }}>
        <CardContent sx={{ p: 4 }}>
          {hasKnownDbs ? (
            <Typography variant="h5" gutterBottom>
              Select Database
            </Typography>
          ) : (
            <>
              <Typography variant="h5" gutterBottom>
                Welcome to NightCrate
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Create your first NightCrate database to get started.
              </Typography>
            </>
          )}

          {/* Show unavailable databases as a warning */}
          {unavailableDbs.length > 0 && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              <Typography variant="body2" gutterBottom>
                The following configured{" "}
                {unavailableDbs.length === 1 ? "database is" : "databases are"}{" "}
                not available:
              </Typography>
              {unavailableDbs.map((db) => (
                <Box key={db.path} sx={{ mt: 0.5 }}>
                  <Typography variant="body2" fontWeight="bold">
                    {db.name}
                  </Typography>
                  <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                    {db.path}
                  </Typography>
                </Box>
              ))}
            </Alert>
          )}

          {/* Show available databases to activate */}
          {hasAvailableDbs && (
            <Box sx={{ mb: 3 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Select an existing database:
              </Typography>
              <List disablePadding sx={{ mb: 1 }}>
                {availableDbs.map((db) => (
                  <ListItemButton
                    key={db.path}
                    onClick={() => void handleActivateExisting(db.path)}
                    disabled={submitting}
                    sx={{ border: 1, borderColor: "divider", borderRadius: 1, mb: 0.5 }}
                  >
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      <StorageIcon fontSize="small" />
                    </ListItemIcon>
                    <ListItemText
                      primary={db.name}
                      secondary={
                        <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                          {db.path}
                        </Typography>
                      }
                    />
                  </ListItemButton>
                ))}
              </List>
              <Divider sx={{ my: 2 }}>
                <Typography variant="caption" color="text.secondary">
                  or create a new database
                </Typography>
              </Divider>
            </Box>
          )}

          <TextField
            label="Database Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            fullWidth
            sx={{ mb: 2 }}
          />
          <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
            <TextField
              label="Location"
              value={directory}
              fullWidth
              slotProps={{
                input: {
                  readOnly: true,
                  endAdornment: !info ? (
                    <CircularProgress size={16} sx={{ mr: 1 }} />
                  ) : null,
                },
              }}
              sx={{ "& .MuiInputBase-input": { cursor: "pointer" } }}
              onClick={() => {
                setBrowsePath(directory || "~");
                setBrowseOpen(true);
              }}
            />
            <Button
              variant="outlined"
              onClick={() => {
                setBrowsePath(directory || "~");
                setBrowseOpen(true);
              }}
              sx={{ whiteSpace: "nowrap", minWidth: 90 }}
            >
              Browse
            </Button>
          </Box>
          {fullPath && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ mb: 3, display: "block", fontFamily: "monospace", wordBreak: "break-all" }}
            >
              {fullPath}
            </Typography>
          )}

          <Button
            variant="contained"
            size="large"
            fullWidth
            onClick={handleSubmit}
            disabled={submitting || !fullPath}
            sx={{ mt: 2 }}
          >
            {submitting ? (
              <CircularProgress size={22} color="inherit" />
            ) : (
              "Create & Start"
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Directory browser dialog */}
      <Dialog
        open={browseOpen}
        onClose={() => setBrowseOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            Select Location
            <Box sx={{ display: "flex", gap: 0.5 }}>
              {shortcuts && (
                <>
                  <Tooltip title="Home">
                    <IconButton
                      size="small"
                      onClick={() => handleBrowseNavigate(shortcuts.home)}
                    >
                      <HomeIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Documents">
                    <IconButton
                      size="small"
                      onClick={() => handleBrowseNavigate(shortcuts.documents)}
                    >
                      <DescriptionIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="App Data">
                    <IconButton
                      size="small"
                      onClick={() => handleBrowseNavigate(shortcuts.app_data)}
                    >
                      <StorageIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </>
              )}
              <Tooltip title="New Folder">
                <IconButton
                  size="small"
                  onClick={() => {
                    setNewFolderName("");
                    setNewFolderOpen(true);
                  }}
                >
                  <CreateNewFolderIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Box>
          </Box>
        </DialogTitle>
        <DialogContent>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ fontFamily: "monospace", display: "block", mb: 1 }}
          >
            {browseResult?.path ?? browsePath}
          </Typography>

          {/* New folder inline form */}
          {newFolderOpen && (
            <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
              <TextField
                size="small"
                label="Folder name"
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                fullWidth
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleCreateFolder();
                  if (e.key === "Escape") setNewFolderOpen(false);
                }}
              />
              <Button
                size="small"
                variant="contained"
                onClick={() => void handleCreateFolder()}
                disabled={!newFolderName.trim()}
              >
                Create
              </Button>
              <Button size="small" onClick={() => setNewFolderOpen(false)}>
                Cancel
              </Button>
            </Box>
          )}

          {browseLoading ? (
            <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
              <CircularProgress />
            </Box>
          ) : (
            <List dense sx={{ maxHeight: 400, overflowY: "auto" }}>
              {/* Parent directory */}
              {browseResult?.path && browseResult.path !== "/" && (
                <ListItemButton
                  onClick={() =>
                    handleBrowseNavigate(
                      browseResult.path.replace(/\/[^/]+\/?$/, "") || "/",
                    )
                  }
                >
                  <ListItemIcon sx={{ minWidth: 36 }}>
                    <FolderIcon />
                  </ListItemIcon>
                  <ListItemText primary=".." />
                </ListItemButton>
              )}
              {browseResult?.dirs.map((dir) => (
                <ListItemButton
                  key={dir.path}
                  onClick={() => handleBrowseNavigate(dir.path)}
                >
                  <ListItemIcon sx={{ minWidth: 36 }}>
                    <FolderIcon />
                  </ListItemIcon>
                  <ListItemText primary={dir.name} />
                </ListItemButton>
              ))}
              {browseResult?.dirs.length === 0 && (
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ py: 2, textAlign: "center" }}
                >
                  No subdirectories
                </Typography>
              )}
            </List>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBrowseOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => handleBrowseSelect(browseResult?.path ?? browsePath)}
          >
            Select This Folder
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={errorMsg !== null}
        autoHideDuration={6000}
        onClose={() => setErrorMsg(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          severity="warning"
          onClose={() => setErrorMsg(null)}
          sx={{ width: "100%" }}
        >
          {errorMsg}
        </Alert>
      </Snackbar>
    </Box>
  );
}
