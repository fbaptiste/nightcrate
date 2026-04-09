import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CreateNewFolderIcon from "@mui/icons-material/CreateNewFolder";
import DescriptionIcon from "@mui/icons-material/Description";
import FolderIcon from "@mui/icons-material/Folder";
import HomeIcon from "@mui/icons-material/Home";
import StorageIcon from "@mui/icons-material/Storage";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAdminInfo,
  fetchAdminStatus,
  createDatabase,
  addExistingDatabase,
  activateDatabase,
  removeDatabase,
  browseForDatabase,
  fetchShortcuts,
  createFolder,
  type AdminStatus,
  type AppInfo,
} from "@/api/admin";

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "unknown";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function nameToFilename(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return slug ? `${slug}.db` : "nightcrate.db";
}

interface InfoRowProps {
  label: string;
  value: string;
}

function InfoRow({ label, value }: InfoRowProps) {
  return (
    <Box sx={{ display: "flex", gap: 2, py: 0.75, alignItems: "baseline" }}>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ minWidth: 160, flexShrink: 0 }}
      >
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>
        {value}
      </Typography>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Create Database Dialog (with folder browser)
// ---------------------------------------------------------------------------

interface CreateDbDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  defaultDir: string;
  title: string;
  isAddExisting?: boolean;
}

function CreateDbDialog({
  open,
  onClose,
  onCreated,
  defaultDir,
  title,
  isAddExisting = false,
}: CreateDbDialogProps) {
  const [name, setName] = useState("");
  const [directory, setDirectory] = useState("");
  const [existingPath, setExistingPath] = useState("");
  const [browseOpen, setBrowseOpen] = useState(false);
  const [browsePath, setBrowsePath] = useState("~");
  const [newFolderName, setNewFolderName] = useState("");
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: shortcuts } = useQuery({
    queryKey: ["admin-shortcuts"],
    queryFn: fetchShortcuts,
  });

  const {
    data: browseResult,
    isLoading: browseLoading,
    refetch: refetchBrowse,
  } = useQuery({
    queryKey: ["admin-browse-dialog", browsePath],
    queryFn: () => browseForDatabase(browsePath),
    enabled: browseOpen,
  });

  const handleOpen = () => {
    setName(isAddExisting ? "" : "My NightCrate Database");
    setDirectory(defaultDir);
    setExistingPath("");
    setError(null);
  };

  const fullPath = directory
    ? `${directory.replace(/\/$/, "")}/${nameToFilename(name)}`
    : "";

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const path = isAddExisting ? existingPath : fullPath;
      if (isAddExisting) {
        await addExistingDatabase({ path, name });
      } else {
        await createDatabase({ path, name });
      }
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operation failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleBrowseSelectDir = (dirPath: string) => {
    setDirectory(dirPath);
    setBrowseOpen(false);
  };

  const handleBrowseSelectFile = (filePath: string) => {
    setExistingPath(filePath);
    // Auto-derive name from filename if empty
    if (!name.trim()) {
      const filename = filePath.split("/").pop() ?? "";
      const base = filename.replace(/\.db$/i, "").replace(/_/g, " ");
      setName(base.charAt(0).toUpperCase() + base.slice(1));
    }
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
      setError(err instanceof Error ? err.message : "Failed to create folder.");
    }
  };

  const isValid = isAddExisting
    ? name.trim() && existingPath.trim()
    : name.trim() && fullPath;

  return (
    <>
      <Dialog
        open={open}
        onClose={onClose}
        fullWidth
        maxWidth="sm"
        TransitionProps={{ onEntered: handleOpen }}
      >
        <DialogTitle>{title}</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 1, display: "flex", flexDirection: "column", gap: 2 }}>
            <TextField
              label="Database Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              fullWidth
              autoFocus
            />
            {isAddExisting ? (
              <Box sx={{ display: "flex", gap: 1 }}>
                <TextField
                  label="Database File"
                  value={existingPath}
                  fullWidth
                  slotProps={{ input: { readOnly: true } }}
                  sx={{ "& .MuiInputBase-input": { cursor: "pointer" } }}
                  onClick={() => {
                    setBrowsePath(defaultDir);
                    setBrowseOpen(true);
                  }}
                  helperText={existingPath ? undefined : "Select an existing .db file"}
                />
                <Button
                  variant="outlined"
                  onClick={() => {
                    setBrowsePath(defaultDir);
                    setBrowseOpen(true);
                  }}
                  sx={{ whiteSpace: "nowrap", minWidth: 90 }}
                >
                  Browse
                </Button>
              </Box>
            ) : (
              <>
                <Box sx={{ display: "flex", gap: 1 }}>
                  <TextField
                    label="Location"
                    value={directory}
                    fullWidth
                    slotProps={{ input: { readOnly: true } }}
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
                    sx={{ fontFamily: "monospace", wordBreak: "break-all", mt: -1 }}
                  >
                    {fullPath}
                  </Typography>
                )}
              </>
            )}
            {error && (
              <Alert severity="error" onClose={() => setError(null)}>
                {error}
              </Alert>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleSubmit}
            disabled={submitting || !isValid}
          >
            {submitting ? <CircularProgress size={20} color="inherit" /> : "Confirm"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Folder browser dialog */}
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
                    <IconButton size="small" onClick={() => handleBrowseNavigate(shortcuts.home)}>
                      <HomeIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Documents">
                    <IconButton size="small" onClick={() => handleBrowseNavigate(shortcuts.documents)}>
                      <DescriptionIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="App Data">
                    <IconButton size="small" onClick={() => handleBrowseNavigate(shortcuts.app_data)}>
                      <StorageIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </>
              )}
              <Tooltip title="New Folder">
                <IconButton size="small" onClick={() => { setNewFolderName(""); setNewFolderOpen(true); }}>
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
              <Button size="small" variant="contained" onClick={() => void handleCreateFolder()} disabled={!newFolderName.trim()}>
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
              {browseResult?.path && browseResult.path !== "/" && (
                <ListItemButton
                  onClick={() =>
                    handleBrowseNavigate(browseResult.path.replace(/\/[^/]+\/?$/, "") || "/")
                  }
                >
                  <ListItemIcon sx={{ minWidth: 36 }}><FolderIcon /></ListItemIcon>
                  <ListItemText primary=".." />
                </ListItemButton>
              )}
              {browseResult?.dirs.map((dir) => (
                <ListItemButton key={dir.path} onClick={() => handleBrowseNavigate(dir.path)}>
                  <ListItemIcon sx={{ minWidth: 36 }}><FolderIcon /></ListItemIcon>
                  <ListItemText primary={dir.name} />
                </ListItemButton>
              ))}
              {/* Show .db files when browsing for existing database */}
              {isAddExisting && browseResult?.files.map((file) => (
                <ListItemButton
                  key={file.path}
                  onClick={() => handleBrowseSelectFile(file.path)}
                >
                  <ListItemIcon sx={{ minWidth: 36 }}><StorageIcon fontSize="small" /></ListItemIcon>
                  <ListItemText
                    primary={file.name}
                    secondary={formatBytes(file.size)}
                  />
                </ListItemButton>
              ))}
              {browseResult?.dirs.length === 0 && (!isAddExisting || browseResult?.files.length === 0) && (
                <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: "center" }}>
                  {isAddExisting ? "No folders or .db files" : "No subdirectories"}
                </Typography>
              )}
            </List>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBrowseOpen(false)}>Cancel</Button>
          {!isAddExisting && (
            <Button variant="contained" onClick={() => handleBrowseSelectDir(browseResult?.path ?? browsePath)}>
              Select This Folder
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </>
  );
}

// ---------------------------------------------------------------------------
// Database Section
// ---------------------------------------------------------------------------

interface DatabaseSectionProps {
  status: AdminStatus;
  onMutate: (action: () => Promise<void>) => void;
}

function DatabaseSection({ status, onMutate }: DatabaseSectionProps) {
  const [createOpen, setCreateOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const queryClient = useQueryClient();

  // Default to the active DB's directory
  const activeDir = status.active_db?.path
    ? status.active_db.path.replace(/\/[^/]+$/, "")
    : "~";

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["admin-status"] });
  };

  const handleActivate = (path: string) => {
    onMutate(async () => {
      await activateDatabase(path);
      window.location.reload();
    });
  };

  const handleRemove = (path: string) => {
    onMutate(async () => {
      await removeDatabase(path);
      invalidate();
    });
  };

  const activeDb = status.active_db;

  return (
    <Box>
      {activeDb && (
        <Box
          sx={{
            mb: 2,
            p: 2,
            borderRadius: 1,
            bgcolor: "primary.main",
            color: "primary.contrastText",
          }}
        >
          <Typography variant="body2" sx={{ opacity: 0.8, mb: 0.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", fontSize: "0.7rem" }}>
            Active Database
          </Typography>
          <Typography variant="body1" fontWeight={600}>
            {activeDb.name}
          </Typography>
          <Typography variant="body2" sx={{ fontFamily: "monospace", opacity: 0.9, wordBreak: "break-all" }}>
            {activeDb.path}
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.8, mt: 0.5 }}>
            {formatBytes(activeDb.size_bytes)}
          </Typography>
        </Box>
      )}

      {status.known_databases.filter((db) => db.path !== activeDb?.path).length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="body2" color="text.secondary" fontWeight={500} sx={{ mb: 1, textTransform: "uppercase", letterSpacing: "0.05em", fontSize: "0.7rem" }}>
            Other Known Databases
          </Typography>
          <List disablePadding>
            {status.known_databases.filter((db) => db.path !== activeDb?.path).map((db) => {
              return (
                <ListItem
                  key={db.path}
                  disablePadding
                  sx={{
                    mb: 1,
                    px: 2,
                    py: 1,
                    borderRadius: 1,
                    border: 1,
                    borderColor: "divider",
                    opacity: db.available ? 1 : 0.55,
                    alignItems: "flex-start",
                  }}
                >
                  <ListItemText
                    primary={
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <Typography variant="body2" fontWeight={500} sx={{ fontStyle: db.available ? "normal" : "italic" }}>
                          {db.name}
                        </Typography>
                        {!db.available && (
                          <Typography variant="caption" color="text.secondary">(not found)</Typography>
                        )}
                      </Box>
                    }
                    secondary={
                      <Box>
                        <Typography
                          component="span"
                          variant="caption"
                          sx={{ fontFamily: "monospace", display: "block", wordBreak: "break-all", fontStyle: db.available ? "normal" : "italic" }}
                        >
                          {db.path}
                        </Typography>
                        {db.available && (
                          <Typography component="span" variant="caption" color="text.secondary">
                            {formatBytes(db.size_bytes)}
                          </Typography>
                        )}
                      </Box>
                    }
                  />
                  <Box sx={{ display: "flex", gap: 1, ml: 1, flexShrink: 0, alignItems: "center", pt: 0.5 }}>
                    <Button size="small" variant="outlined" disabled={!db.available} onClick={() => handleActivate(db.path)}>
                      Activate
                    </Button>
                    <Button size="small" variant="outlined" color="warning" onClick={() => handleRemove(db.path)}>
                      Remove
                    </Button>
                  </Box>
                </ListItem>
              );
            })}
          </List>
        </Box>
      )}

      <Box sx={{ display: "flex", gap: 2 }}>
        <Button variant="contained" onClick={() => setCreateOpen(true)}>
          Create New Database
        </Button>
        <Button variant="outlined" onClick={() => setAddOpen(true)}>
          Add Existing Database
        </Button>
      </Box>

      <CreateDbDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={invalidate}
        defaultDir={activeDir}
        title="Create New Database"
      />
      <CreateDbDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={invalidate}
        defaultDir={activeDir}
        title="Add Existing Database"
        isAddExisting
      />
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Admin Page
// ---------------------------------------------------------------------------

export function AdminPage() {
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const infoQuery = useQuery({
    queryKey: ["admin-info"],
    queryFn: fetchAdminInfo,
  });

  const statusQuery = useQuery({
    queryKey: ["admin-status"],
    queryFn: fetchAdminStatus,
  });

  const info: AppInfo | undefined = infoQuery.data;
  const status: AdminStatus | undefined = statusQuery.data;

  const handleMutate = async (action: () => Promise<void>) => {
    try {
      await action();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Operation failed.");
    }
  };

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: "auto" }}>
      <Typography variant="h5" sx={{ mb: 3 }}>
        Admin
      </Typography>

      <Typography variant="h6" sx={{ mb: 1 }}>
        App Info
      </Typography>
      <Paper sx={{ p: 2, mb: 3 }}>
        {infoQuery.isLoading && <CircularProgress size={20} />}
        {info && (
          <Box>
            <InfoRow label="Config File" value={info.config_file} />
            <InfoRow label="App Data Directory" value={info.app_data_dir} />
            <InfoRow label="Backend Root" value={info.backend_root} />
            <InfoRow label="Seed Data" value={info.seed_data_dir} />
            <InfoRow label="Python Version" value={info.python_version} />
            <InfoRow label="App Version" value={info.app_version} />
          </Box>
        )}
      </Paper>

      <Typography variant="h6" sx={{ mb: 1 }}>
        Database Management
      </Typography>
      <Paper sx={{ p: 2 }}>
        {statusQuery.isLoading && <CircularProgress size={20} />}
        {status && <DatabaseSection status={status} onMutate={handleMutate} />}
      </Paper>

      <Snackbar
        open={errorMsg !== null}
        autoHideDuration={6000}
        onClose={() => setErrorMsg(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="error" onClose={() => setErrorMsg(null)} sx={{ width: "100%" }}>
          {errorMsg}
        </Alert>
      </Snackbar>
    </Box>
  );
}
