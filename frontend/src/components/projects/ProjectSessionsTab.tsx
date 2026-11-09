import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import AddIcon from "@mui/icons-material/Add";
import AutorenewIcon from "@mui/icons-material/Autorenew";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";
import { fetchFilters } from "@/api/equipment";
import { fetchProject, fetchProjectRigSetups } from "@/api/projects";
import { fetchRigs } from "@/api/rigs";
import {
  createSession,
  deleteSession,
  deriveSessions,
  getIntegration,
  listNightNotes,
  listSessions,
  updateSession,
  updateSessionSetup,
  type ProjectSession,
  type SessionCreate,
} from "@/api/projectSessions";
import ExposureTable from "./ExposureTable";
import FilterSwatch from "./FilterSwatch";
import { formatHoursMinutes } from "./IntegrationBars";
import NightNoteDialog from "./NightNoteDialog";
import SessionFormDialog from "./SessionFormDialog";
import SessionNightBlock, { type SessionRigGroup } from "./SessionNightBlock";
import { compareFilters, resolveFilter, summarizeSessionFilters } from "./filterColors";

interface Props {
  projectId: number;
  focusNight?: string;
}

const shortDateFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

function formatShortDate(date: string): string {
  return shortDateFormatter.format(new Date(`${date.slice(0, 10)}T00:00:00Z`));
}

function formatSpan(first: string, last: string): string {
  const firstDate = new Date(`${first.slice(0, 10)}T00:00:00Z`);
  const lastDate = new Date(`${last.slice(0, 10)}T00:00:00Z`);
  if (
    firstDate.getUTCFullYear() === lastDate.getUTCFullYear() &&
    firstDate.getUTCMonth() === lastDate.getUTCMonth()
  ) {
    return `${firstDate.getUTCDate()} – ${shortDateFormatter.format(lastDate)}`;
  }
  return `${shortDateFormatter.format(firstDate)} – ${shortDateFormatter.format(lastDate)}`;
}

interface NightBlockData {
  key: string;
  night: string | null;
  rigGroups: SessionRigGroup[];
}

export default function ProjectSessionsTab({ projectId, focusNight }: Props) {
  const queryClient = useQueryClient();
  const [snack, setSnack] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ProjectSession | null>(null);
  const [confirmDerive, setConfirmDerive] = useState(false);
  const [noteNight, setNoteNight] = useState<string | null>(null);
  const nightRefs = useRef(new Map<string, HTMLElement>());

  const { data: sessions = [], isLoading: sessionsLoading } = useQuery({
    queryKey: ["project-sessions", projectId],
    queryFn: () => listSessions(projectId),
  });
  const { data: nightNotes = [], isLoading: notesLoading } = useQuery({
    queryKey: ["project-night-notes", projectId],
    queryFn: () => listNightNotes(projectId),
  });
  const { data: integration } = useQuery({
    queryKey: ["project-integration", projectId],
    queryFn: () => getIntegration(projectId),
  });
  const { data: allRigs = [] } = useQuery({
    queryKey: ["rigs", "all"],
    queryFn: () => fetchRigs(false),
  });
  const { data: filters = [] } = useQuery({
    queryKey: ["filters"],
    queryFn: () => fetchFilters(false, false),
  });
  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => fetchProject(projectId),
  });
  const { data: projectRigSetups = [] } = useQuery({
    queryKey: ["project-rig-setups", projectId],
    queryFn: () => fetchProjectRigSetups(projectId),
  });

  const rigs = useMemo(() => {
    const usedIds = new Set([
      ...(project?.rigs.map((rig) => rig.id) ?? []),
      ...projectRigSetups.map((rig) => rig.rig_id),
    ]);
    return allRigs.filter((rig) => (rig.active && rig.is_mine) || usedIds.has(rig.id));
  }, [allRigs, project, projectRigSetups]);
  const projectRigs = useMemo(() => {
    const ids = new Set(project?.rigs.map((rig) => rig.id) ?? []);
    return rigs.filter((rig) => ids.has(rig.id));
  }, [project, rigs]);
  const setupByRig = useMemo(
    () => new Map(projectRigSetups.map((history) => [history.rig_id, history])),
    [projectRigSetups],
  );
  const noteByNight = useMemo(
    () => new Map(nightNotes.map((note) => [note.night_date, note.notes])),
    [nightNotes],
  );
  const filtersById = useMemo(
    () => new Map(filters.map((filter) => [filter.id, filter])),
    [filters],
  );

  const blocks = useMemo<NightBlockData[]>(() => {
    const nights = new Map<string | null, Map<number | null, ProjectSession[]>>();
    for (const session of sessions) {
      const night = session.session_date?.slice(0, 10) ?? null;
      const rigsForNight = nights.get(night) ?? new Map<number | null, ProjectSession[]>();
      const group = rigsForNight.get(session.rig_id) ?? [];
      group.push(session);
      rigsForNight.set(session.rig_id, group);
      nights.set(night, rigsForNight);
    }
    for (const note of nightNotes) {
      if (!nights.has(note.night_date)) nights.set(note.night_date, new Map());
    }

    return Array.from(nights)
      .sort(([a], [b]) => {
        if (a == null) return 1;
        if (b == null) return -1;
        return b.localeCompare(a);
      })
      .map(([night, rigGroups]) => ({
        key: night ?? "none",
        night,
        rigGroups: Array.from(rigGroups, ([rigId, groupedSessions]) => ({
          rigId,
          rigName: groupedSessions[0]?.rig_name ?? "No rig",
          sessions: groupedSessions,
          setupOptions: rigId == null
            ? []
            : setupByRig.get(rigId)?.setup_options ?? [],
        })),
      }));
  }, [nightNotes, sessions, setupByRig]);

  useEffect(() => {
    if (!focusNight || sessionsLoading || notesLoading) return;
    const block = nightRefs.current.get(focusNight);
    if (!block) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    block.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "center" });
  }, [blocks, focusNight, notesLoading, sessionsLoading]);

  const { derivedCount, manualCount, lastDerived } = useMemo(() => {
    let derived = 0;
    let latest: string | null = null;
    for (const session of sessions) {
      if (session.source !== "auto") continue;
      derived += 1;
      if (latest === null || session.created_at > latest) latest = session.created_at;
    }
    return { derivedCount: derived, manualCount: sessions.length - derived, lastDerived: latest };
  }, [sessions]);

  const caption = derivedCount > 0 && integration
    ? `${derivedCount} batch${derivedCount === 1 ? "" : "es"} over ${integration?.night_count ?? 0} night${integration?.night_count === 1 ? "" : "s"}, built from the cataloged subs${lastDerived ? ` on ${formatShortDate(lastDerived)}` : ""}${manualCount > 0 ? `, ${manualCount} added by hand` : ""}`
    : derivedCount === 0 && manualCount > 0
      ? `${manualCount} added by hand`
      : null;

  const filterTotals = useMemo(
    () => summarizeSessionFilters(sessions, filtersById),
    [filtersById, sessions],
  );
  const totalSubs = sessions.reduce((sum, session) => sum + session.num_subs, 0);
  // The exposure table lists filters as shot: an equipment filter by its model
  // name, so look the name up to sort a dual-band filter by its lines.
  const sortedExposures = useMemo(() => {
    const filtersByName = new Map(filters.map((filter) => [filter.model_name, filter]));
    return [...(integration?.exposures ?? [])]
      .map((line) => ({
        line,
        resolved: resolveFilter({
          label: line.label,
          equipmentFilter: filtersByName.get(line.label) ?? null,
        }),
      }))
      .sort(
        (a, b) =>
          compareFilters(a.resolved, b.resolved) ||
          a.line.label.localeCompare(b.line.label, undefined, { sensitivity: "base" }) ||
          a.line.exposure_seconds - b.line.exposure_seconds,
      )
      .map(({ line }) => line);
  }, [filters, integration]);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["rigs"] });
    queryClient.invalidateQueries({ queryKey: ["rig-setups"] });
    queryClient.invalidateQueries({ queryKey: ["project-rig-setups", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-catalog", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-sessions", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-integration", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-solve", projectId] });
    queryClient.invalidateQueries({ queryKey: ["equipment-usage"] });
  };

  const setupMut = useMutation({
    mutationFn: ({ sessionId, rigSetupId }: { sessionId: number; rigSetupId: number | null }) =>
      updateSessionSetup(projectId, sessionId, rigSetupId),
    onSuccess: () => {
      refresh();
      setSnack("Session setup updated");
    },
    onError: (error) => setSnack(String(error)),
  });
  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteSession(projectId, id),
    onSuccess: () => {
      refresh();
      setSnack("Session removed");
    },
    onError: (error) => setSnack(String(error)),
  });
  const deriveMut = useMutation({
    mutationFn: () => deriveSessions(projectId),
    onSuccess: (result) => {
      refresh();
      const skipped = result.lights_skipped
        ? `, ${result.lights_skipped} skipped (no exposure time)`
        : "";
      setSnack(
        result.sessions_created === 0
          ? `No sessions rebuilt — this project has no cataloged light frames${skipped}`
          : `Rebuilt ${result.sessions_created} session${result.sessions_created === 1 ? "" : "s"} from ${result.lights_considered} light frames${skipped}`,
      );
    },
    onError: (error) => setSnack(String(error)),
  });

  const handleSubmit = async (body: SessionCreate) => {
    if (editing) await updateSession(projectId, editing.id, body);
    else await createSession(projectId, body);
    refresh();
    setSnack(editing ? "Session updated" : "Session added");
  };

  if (sessionsLoading || notesLoading) {
    return <Box sx={{ p: 2 }}><CircularProgress size={24} /></Box>;
  }

  return (
    <Box sx={{ width: "100%", maxWidth: 1120, minWidth: 0 }}>
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="h6">Imaging sessions</Typography>
          {caption && (
            <Typography sx={{ color: "text.secondary", fontSize: "13px" }}>{caption}.</Typography>
          )}
        </Box>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          <Button
            variant="outlined"
            size="small"
            startIcon={deriveMut.isPending ? <CircularProgress size={14} /> : <AutorenewIcon />}
            onClick={() => (derivedCount > 0 ? setConfirmDerive(true) : deriveMut.mutate())}
            disabled={deriveMut.isPending}
          >
            {deriveMut.isPending ? "Rebuilding…" : "Rebuild from subs"}
          </Button>
          <Button
            variant="contained"
            size="small"
            startIcon={<AddIcon />}
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            Add by hand
          </Button>
        </Box>
      </Box>

      {integration && sessions.length > 0 && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap", my: "14px", mb: "18px" }}>
          <Typography sx={{ fontSize: "15px" }}>
            <Box component="span" sx={{ fontSize: "17px", fontWeight: 600 }}>
              {formatHoursMinutes(integration.total_actual_minutes)}
            </Box>{" "}
            in {totalSubs} sub{totalSubs === 1 ? "" : "s"} over {integration.night_count} night{integration.night_count === 1 ? "" : "s"}
            {integration.first_session_date && integration.last_session_date
              ? `, ${formatSpan(integration.first_session_date, integration.last_session_date)}`
              : ""}
          </Typography>
          <Box sx={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
            {filterTotals.map((filter) => (
              <Box
                key={filter.key}
                sx={(currentTheme) => ({
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  height: "24px",
                  px: "10px",
                  border: 1,
                  borderColor: currentTheme.palette.mode === "dark" ? "#4a4d54" : "#c4c1bb",
                  borderRadius: "12px",
                  fontSize: "12.5px",
                })}
              >
                <FilterSwatch filter={filter} />
                {filter.label} {formatHoursMinutes(filter.minutes)}
              </Box>
            ))}
          </Box>
        </Box>
      )}

      {blocks.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
          No sessions yet. Add one by hand, or rebuild from subs using the light frames you have already cataloged.
        </Typography>
      ) : (
        blocks.map((block, index) => {
          const focusKey = block.night ?? "none";
          return (
            <SessionNightBlock
              key={block.key}
              sectionRef={(node) => {
                if (node) nightRefs.current.set(focusKey, node);
                else nightRefs.current.delete(focusKey);
              }}
              headingId={`session-night-${index}`}
              night={block.night}
              rigGroups={block.rigGroups}
              filtersById={filtersById}
              nightNote={block.night ? noteByNight.get(block.night) ?? null : null}
              highlighted={focusNight === focusKey}
              setupPending={setupMut.isPending}
              onChangeSetup={(sessionId, rigSetupId) => setupMut.mutate({ sessionId, rigSetupId })}
              onEditSession={(session) => {
                setEditing(session);
                setFormOpen(true);
              }}
              onDeleteSession={(sessionId) => deleteMut.mutate(sessionId)}
              onEditNote={() => block.night && setNoteNight(block.night)}
            />
          );
        })
      )}

      {integration && integration.exposures.length > 0 && (
        <>
          <Divider sx={{ my: 4 }} />
          <ExposureTable lines={sortedExposures} />
        </>
      )}

      {formOpen && (
        <SessionFormDialog
          key={editing?.id ?? "new"}
          open
          onClose={() => setFormOpen(false)}
          session={editing}
          rigs={rigs}
          filters={filters}
          projectRigs={projectRigs}
          projectRigSetups={projectRigSetups}
          onSubmit={handleSubmit}
        />
      )}

      {noteNight && (
        <NightNoteDialog
          key={noteNight}
          projectId={projectId}
          night={noteNight}
          note={noteByNight.get(noteNight) ?? null}
          open
          onClose={() => setNoteNight(null)}
        />
      )}

      <Dialog open={confirmDerive} onClose={() => setConfirmDerive(false)}>
        <DialogTitle>Replace derived sessions?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            This deletes the {derivedCount} derived session{derivedCount === 1 ? "" : "s"} and rebuilds them from this project&apos;s cataloged light frames.
            {manualCount > 0 && ` Your ${manualCount} hand-entered session${manualCount === 1 ? " is" : "s are"} left untouched.`}
            {" Night notes are kept."}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDerive(false)}>Cancel</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              setConfirmDerive(false);
              deriveMut.mutate();
            }}
          >
            Rebuild
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={Boolean(snack)} autoHideDuration={3000} onClose={() => setSnack(null)} message={snack} />
    </Box>
  );
}
