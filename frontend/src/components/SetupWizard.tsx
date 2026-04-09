import { useState, useEffect } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CircularProgress from "@mui/material/CircularProgress";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { fetchAdminInfo, fetchAdminStatus, setupDatabase } from "@/api/admin";

export function SetupWizard() {
  const [name, setName] = useState("My Equipment Database");
  const [path, setPath] = useState("");
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

  useEffect(() => {
    if (info && !path) {
      setPath(`${info.app_data_dir}/nightcrate.db`);
    }
  }, [info, path]);

  const isScenarioB =
    status !== undefined &&
    status.known_databases.length > 0 &&
    !status.known_databases.some((db) => db.available);

  const unavailableDbs =
    isScenarioB ? status!.known_databases.filter((db) => !db.available) : [];

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await setupDatabase({ path, name });
      window.location.reload();
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Failed to create database.",
      );
    } finally {
      setSubmitting(false);
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
          {isScenarioB ? (
            <>
              <Typography variant="h5" gutterBottom>
                Database Not Available
              </Typography>
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
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Create a new database or go to Admin to manage your database
                list.
              </Typography>
            </>
          ) : (
            <>
              <Typography variant="h5" gutterBottom>
                Welcome to NightCrate
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Create your first equipment database to get started.
              </Typography>
            </>
          )}

          <TextField
            label="Database Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            fullWidth
            sx={{ mb: 2 }}
          />
          <TextField
            label="Database Path"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            fullWidth
            sx={{ mb: 3 }}
            slotProps={{
              input: {
                endAdornment: !info ? (
                  <CircularProgress size={16} sx={{ mr: 1 }} />
                ) : null,
              },
            }}
          />

          <Button
            variant="contained"
            size="large"
            fullWidth
            onClick={handleSubmit}
            disabled={submitting || !path}
          >
            {submitting ? (
              <CircularProgress size={22} color="inherit" />
            ) : isScenarioB ? (
              "Create New Database"
            ) : (
              "Create & Start"
            )}
          </Button>
        </CardContent>
      </Card>

      <Snackbar
        open={errorMsg !== null}
        autoHideDuration={6000}
        onClose={() => setErrorMsg(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          severity="error"
          onClose={() => setErrorMsg(null)}
          sx={{ width: "100%" }}
        >
          {errorMsg}
        </Alert>
      </Snackbar>
    </Box>
  );
}
