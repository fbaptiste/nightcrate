import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAdminInfo,
  fetchAdminStatus,
  createDatabase,
  activateDatabase,
  removeDatabase,
  type AdminStatus,
  type AppInfo,
} from "@/api/admin";

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "unknown";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
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
  const [path, setPath] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleOpen = () => {
    setName(isAddExisting ? "" : "My Database");
    setPath(isAddExisting ? "" : `${defaultDir}/nightcrate.db`);
    setError(null);
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await createDatabase({ path, name });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operation failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
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
          <TextField
            label="Database Path"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            fullWidth
            helperText={
              isAddExisting
                ? "Full path to an existing .db file"
                : "Full path where the new database file will be created"
            }
          />
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
          disabled={submitting || !name.trim() || !path.trim()}
        >
          {submitting ? <CircularProgress size={20} color="inherit" /> : "Confirm"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

interface DatabaseSectionProps {
  status: AdminStatus;
  onMutate: (action: () => Promise<void>) => void;
}

function DatabaseSection({ status, onMutate }: DatabaseSectionProps) {
  const [createOpen, setCreateOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const queryClient = useQueryClient();

  const infoQuery = useQuery({
    queryKey: ["admin-info"],
    queryFn: fetchAdminInfo,
  });
  const defaultDir = infoQuery.data?.app_data_dir ?? "~";

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-status"] });
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
      {/* Current database highlight */}
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

      {/* All known databases */}
      {status.known_databases.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="body2" color="text.secondary" fontWeight={500} sx={{ mb: 1, textTransform: "uppercase", letterSpacing: "0.05em", fontSize: "0.7rem" }}>
            Known Databases
          </Typography>
          <List disablePadding>
            {status.known_databases.map((db) => {
              const isActive = activeDb?.path === db.path;
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
                    borderColor: isActive ? "primary.main" : "divider",
                    opacity: db.available ? 1 : 0.55,
                    alignItems: "flex-start",
                  }}
                >
                  <ListItemText
                    primary={
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <Typography
                          variant="body2"
                          fontWeight={500}
                          sx={{ fontStyle: db.available ? "normal" : "italic" }}
                        >
                          {db.name}
                        </Typography>
                        {!db.available && (
                          <Typography variant="caption" color="text.secondary">
                            (not found)
                          </Typography>
                        )}
                        {isActive && (
                          <Typography variant="caption" color="primary.main" fontWeight={600}>
                            active
                          </Typography>
                        )}
                      </Box>
                    }
                    secondary={
                      <Box>
                        <Typography
                          component="span"
                          variant="caption"
                          sx={{
                            fontFamily: "monospace",
                            display: "block",
                            wordBreak: "break-all",
                            fontStyle: db.available ? "normal" : "italic",
                          }}
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
                    <Button
                      size="small"
                      variant="outlined"
                      disabled={isActive || !db.available}
                      onClick={() => handleActivate(db.path)}
                    >
                      Activate
                    </Button>
                    <Button
                      size="small"
                      variant="outlined"
                      color="warning"
                      disabled={isActive}
                      onClick={() => handleRemove(db.path)}
                    >
                      Remove
                    </Button>
                  </Box>
                </ListItem>
              );
            })}
          </List>
        </Box>
      )}

      {/* Actions */}
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
        defaultDir={defaultDir}
        title="Create New Database"
      />
      <CreateDbDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={invalidate}
        defaultDir={defaultDir}
        title="Add Existing Database"
        isAddExisting
      />
    </Box>
  );
}

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

      {/* App Info Section */}
      <Typography variant="h6" sx={{ mb: 1 }}>
        App Info
      </Typography>
      <Paper sx={{ p: 2, mb: 3 }}>
        {infoQuery.isLoading && (
          <CircularProgress size={20} />
        )}
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

      {/* Database Management Section */}
      <Typography variant="h6" sx={{ mb: 1 }}>
        Database Management
      </Typography>
      <Paper sx={{ p: 2 }}>
        {statusQuery.isLoading && <CircularProgress size={20} />}
        {status && (
          <DatabaseSection status={status} onMutate={handleMutate} />
        )}
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
