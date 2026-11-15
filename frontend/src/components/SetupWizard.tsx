import { useState, useEffect } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CircularProgress from "@mui/material/CircularProgress";
import Checkbox from "@mui/material/Checkbox";
import Divider from "@mui/material/Divider";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import FormControlLabel from "@mui/material/FormControlLabel";
import StorageIcon from "@mui/icons-material/Storage";
import { useQuery } from "@tanstack/react-query";
import {
  fetchAdminInfo,
  fetchAdminStatus,
  setupDatabase,
  activateDatabase,
} from "@/api/admin";
import { setCheckAutomatically } from "@/api/updates";
import { FileBrowser } from "@/components/fits/FileBrowser";
import { joinPath } from "@/lib/paths";

/** Convert a workspace name to a folder slug (e.g., "Fred's Rig" → "Freds_Rig") */
function nameToFolder(name: string): string {
  const slug = name
    .replace(/[^a-zA-Z0-9 ]+/g, "")
    .trim()
    .replace(/ +/g, "_");
  return slug || "NightCrate";
}

export function SetupWizard() {
  const [name, setName] = useState("My NightCrate");
  const [directory, setDirectory] = useState("");
  const [browseOpen, setBrowseOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [automaticChecks, setAutomaticChecks] = useState(true);

  const { data: info } = useQuery({
    queryKey: ["adminInfo"],
    queryFn: fetchAdminInfo,
  });

  const { data: status } = useQuery({
    queryKey: ["adminStatus"],
    queryFn: fetchAdminStatus,
  });

  useEffect(() => {
    if (info && !directory) {
      setDirectory(info.app_data_dir);
    }
  }, [info, directory]);

  const fullPath = directory ? joinPath(directory, nameToFolder(name)) : "";

  const knownDbs = status?.known_databases ?? [];
  const availableDbs = knownDbs.filter((db) => db.available);
  const unavailableDbs = knownDbs.filter((db) => !db.available);
  const hasKnownDbs = knownDbs.length > 0;
  const hasAvailableDbs = availableDbs.length > 0;

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await setupDatabase({ path: fullPath, name });
      await setCheckAutomatically(automaticChecks);
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
                Create your first NightCrate workspace to get started.
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
            label="Workspace Name"
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
              onClick={() => setBrowseOpen(true)}
            />
            <Button
              variant="outlined"
              onClick={() => setBrowseOpen(true)}
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

          {!hasKnownDbs && (
            <Box sx={{ p: 1.5, bgcolor: "background.default", borderRadius: 1.5 }}>
              <FormControlLabel
                control={<Checkbox checked={automaticChecks} onChange={(event) => setAutomaticChecks(event.target.checked)} />}
                label={<Box><Typography fontWeight={600} variant="body2">Check for new versions automatically</Typography><Typography color="text.secondary" variant="caption">Once a day, NightCrate asks GitHub whether a newer version of NightCrate or of the OpenNGC catalog exists. It sends nothing about your images or workspaces. You can change this later in Admin.</Typography></Box>}
                sx={{ alignItems: "flex-start", m: 0 }}
              />
            </Box>
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

      <FileBrowser
        open={browseOpen}
        onClose={() => setBrowseOpen(false)}
        onSelect={handleBrowseSelect}
        title="Select Location"
        emptyMessage="No folders here"
        accept={[".db"]}
        directoryMode
        plainFolders
        allowNewFolder
        startPath={directory || "~"}
      />

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
