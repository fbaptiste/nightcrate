import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import NotesIcon from "@mui/icons-material/Notes";
import { fetchRigs } from "@/api/rigs";
import { fetchFilters } from "@/api/equipment";
import { fetchProject } from "@/api/projects";
import {
  type FilterGoal,
  type ProjectSession,
  type SessionCreate,
  createSession,
  deleteSession,
  getIntegration,
  listSessions,
  setFilterGoals,
  updateSession,
} from "@/api/projectSessions";
import IntegrationBars, { formatHoursMinutes } from "./IntegrationBars";
import FilterGoalsEditor from "./FilterGoalsEditor";
import SessionFormDialog from "./SessionFormDialog";

interface Props {
  projectId: number;
}

export default function ProjectSessionsTab({ projectId }: Props) {
  const queryClient = useQueryClient();
  const [snack, setSnack] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ProjectSession | null>(null);

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["project-sessions", projectId],
    queryFn: () => listSessions(projectId),
  });
  const { data: integration } = useQuery({
    queryKey: ["project-integration", projectId],
    queryFn: () => getIntegration(projectId),
  });
  const { data: rigs = [] } = useQuery({ queryKey: ["rigs"], queryFn: () => fetchRigs(true) });
  const { data: filters = [] } = useQuery({
    queryKey: ["filters"],
    queryFn: () => fetchFilters(false, false),
  });
  // The project's rigs (full Rig objects) — used to surface their loaded
  // filters at the top of the filter pickers.
  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => fetchProject(projectId),
  });

  const projectRigs = useMemo(() => {
    const ids = new Set(project?.rigs.map((r) => r.id) ?? []);
    return rigs.filter((r) => ids.has(r.id));
  }, [project, rigs]);

  const rigFilterIds = useMemo(() => {
    const ids = new Set<number>();
    for (const rig of projectRigs) {
      for (const slot of rig.filter_slots) ids.add(slot.filter_id);
      if (rig.single_filter_id != null) ids.add(rig.single_filter_id);
    }
    return ids;
  }, [projectRigs]);

  const rigLineNames = useMemo(() => {
    const names = new Set<string>();
    for (const rig of projectRigs) {
      for (const slot of rig.filter_slots) {
        for (const pb of slot.passbands) names.add(pb);
      }
      if (rig.single_filter_id != null) {
        const f = filters.find((x) => x.id === rig.single_filter_id);
        if (f) for (const pb of f.passbands) if (pb.line_name) names.add(pb.line_name);
      }
    }
    return names;
  }, [projectRigs, filters]);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["project-sessions", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-integration", projectId] });
  };

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteSession(projectId, id),
    onSuccess: () => {
      refresh();
      setSnack("Session removed");
    },
    onError: (e) => setSnack(String(e)),
  });

  const goalsMut = useMutation({
    mutationFn: (goals: FilterGoal[]) => setFilterGoals(projectId, goals),
    onSuccess: (summary) => {
      queryClient.setQueryData(["project-integration", projectId], summary);
    },
    onError: (e) => setSnack(String(e)),
  });

  const handleSubmit = async (body: SessionCreate) => {
    if (editing) {
      await updateSession(projectId, editing.id, body);
    } else {
      await createSession(projectId, body);
    }
    refresh();
    setSnack(editing ? "Session updated" : "Session added");
  };

  if (isLoading) {
    return (
      <Box sx={{ p: 2 }}>
        <CircularProgress size={24} />
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 900 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
        <Typography variant="h6">Imaging Sessions</Typography>
        <Button
          variant="contained"
          size="small"
          startIcon={<AddIcon />}
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
          sx={{ ml: "50px" }}
        >
          Add session
        </Button>
      </Box>

      {sessions.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
          No sessions yet. Add one to start tracking integration time.
        </Typography>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Date</TableCell>
              <TableCell>Filter</TableCell>
              <TableCell align="right">Exp (s)</TableCell>
              <TableCell align="right">Gain</TableCell>
              <TableCell align="right">Subs</TableCell>
              <TableCell align="right">Bin</TableCell>
              <TableCell align="right">Time</TableCell>
              <TableCell>Rig</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {sessions.map((s) => (
              <TableRow key={s.id} hover>
                <TableCell>{s.session_date?.slice(0, 10) ?? "—"}</TableCell>
                <TableCell>
                  {s.filter_name ?? s.line_name ?? "—"}
                  {s.notes && (
                    <Tooltip title={s.notes}>
                      <NotesIcon fontSize="inherit" sx={{ ml: 0.5, verticalAlign: "middle" }} />
                    </Tooltip>
                  )}
                </TableCell>
                <TableCell align="right">{s.exposure_seconds}</TableCell>
                <TableCell align="right">{s.gain ?? "—"}</TableCell>
                <TableCell align="right">{s.num_subs}</TableCell>
                <TableCell align="right">
                  {s.binning != null ? `${s.binning}x${s.binning}` : "—"}
                </TableCell>
                <TableCell align="right">{formatHoursMinutes(s.integration_minutes)}</TableCell>
                <TableCell>{s.rig_name ?? "—"}</TableCell>
                <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                  <IconButton
                    size="small"
                    aria-label="Edit session"
                    onClick={() => {
                      setEditing(s);
                      setFormOpen(true);
                    }}
                  >
                    <EditIcon fontSize="small" />
                  </IconButton>
                  <IconButton
                    size="small"
                    aria-label="Delete session"
                    onClick={() => deleteMut.mutate(s.id)}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Divider sx={{ my: 5 }} />

      <Box sx={{ display: "flex", flexDirection: "column", gap: 5 }}>
        {integration && <IntegrationBars summary={integration} />}
        {integration && (
          <FilterGoalsEditor
            summary={integration}
            rigLineNames={rigLineNames}
            onCommit={(g) => goalsMut.mutate(g)}
          />
        )}
      </Box>

      {formOpen && (
        <SessionFormDialog
          key={editing?.id ?? "new"}
          open
          onClose={() => setFormOpen(false)}
          session={editing}
          rigs={rigs}
          filters={filters}
          rigFilterIds={rigFilterIds}
          projectRigs={projectRigs}
          onSubmit={handleSubmit}
        />
      )}

      <Snackbar
        open={!!snack}
        autoHideDuration={3000}
        onClose={() => setSnack(null)}
        message={snack}
      />
    </Box>
  );
}
