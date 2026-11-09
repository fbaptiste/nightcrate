import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import { fetchProjectRigSetups } from "@/api/projects";
import {
  listNightNotes,
  listSessions,
  type ProjectSession,
} from "@/api/projectSessions";
import MarkdownEditor from "@/components/common/MarkdownEditor";
import { formatNight } from "@/lib/localDate";
import { setupLabel } from "./setupLabel";

interface Props {
  projectId: number;
  notes: string;
  onSave: (notes: string) => void;
  onOpenNight: (night: string) => void;
}

function filterLabel(session: ProjectSession): string {
  return session.filter_label ?? session.filter_name ?? session.line_name ?? "Unknown filter";
}

export default function ProjectNotesTab({ projectId, notes, onSave, onOpenNight }: Props) {
  const { data: sessions = [] } = useQuery({
    queryKey: ["project-sessions", projectId],
    queryFn: () => listSessions(projectId),
  });
  const { data: nightNotes = [] } = useQuery({
    queryKey: ["project-night-notes", projectId],
    queryFn: () => listNightNotes(projectId),
  });
  const { data: rigSetups = [] } = useQuery({
    queryKey: ["project-rig-setups", projectId],
    queryFn: () => fetchProjectRigSetups(projectId),
  });
  const setupByRig = useMemo(
    () => new Map(rigSetups.map((history) => [history.rig_id, history])),
    [rigSetups],
  );

  const items = useMemo(() => {
    const noteByNight = new Map(nightNotes.map((note) => [note.night_date, note.notes]));
    const keys = new Set<string | null>(nightNotes.map((note) => note.night_date));
    for (const session of sessions) {
      if (session.source === "manual" && session.notes?.trim()) {
        keys.add(session.session_date?.slice(0, 10) ?? null);
      }
    }

    return Array.from(keys)
      .sort((a, b) => {
        if (a == null) return 1;
        if (b == null) return -1;
        return b.localeCompare(a);
      })
      .map((night) => {
        const nightSessions = sessions.filter(
          (session) => (session.session_date?.slice(0, 10) ?? null) === night,
        );
        const manualNotes = nightSessions.filter(
          (session) => session.source === "manual" && Boolean(session.notes?.trim()),
        );
        const rigGroups = new Map<number | null, ProjectSession[]>();
        for (const session of nightSessions) {
          const group = rigGroups.get(session.rig_id) ?? [];
          group.push(session);
          rigGroups.set(session.rig_id, group);
        }
        const rigs = Array.from(rigGroups, ([rigId, rigSessions]) => {
          const name = rigSessions[0].rig_name ?? "No rig";
          if (rigId == null) return name;
          const history = setupByRig.get(rigId);
          if (!history || history.setup_options.length <= 1) return name;
          const setupId = rigSessions[0].rig_setup_id;
          const mixed = rigSessions.some((session) => session.rig_setup_id !== setupId);
          if (mixed) return `${name}, mixed setups`;
          const option = history.setup_options.find((candidate) => candidate.rig_setup_id === setupId);
          const label = setupLabel(option?.until_at);
          return `${name}, ${label.charAt(0).toLowerCase()}${label.slice(1)}`;
        });
        return {
          night,
          nightNote: night ? noteByNight.get(night) ?? null : null,
          manualNotes,
          rigs,
        };
      });
  }, [nightNotes, sessions, setupByRig]);

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) 320px",
        gap: "22px",
        alignItems: "start",
        maxWidth: 1120,
        "@media (max-width: 899.95px)": { gridTemplateColumns: "minmax(0, 1fr)" },
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        <MarkdownEditor
          value={notes}
          onSave={(next) => onSave(next.trim())}
          label={
            <Typography variant="subtitle2" color="text.secondary">
              Notes
            </Typography>
          }
          placeholder="Add notes"
        />
      </Box>

      <Box
        sx={(theme) => ({
          bgcolor: "background.paper",
          border: 1,
          borderColor: theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4",
          borderRadius: "8px",
          px: "16px",
          py: "14px",
        })}
      >
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mb: items.length ? 0 : 1 }}>
          <Typography sx={{ fontSize: "15px", fontWeight: 600 }}>Night notes</Typography>
          <Typography sx={{ color: "text.secondary", fontSize: "12.5px" }}>from Sessions</Typography>
        </Box>
        {items.length === 0 ? (
          <Typography sx={{ color: "text.secondary", fontSize: "13px" }}>
            No night notes yet. Add one from a night on the Sessions tab.
          </Typography>
        ) : (
          items.map((item) => {
            const label = item.night ? formatNight(item.night) : "No date";
            return (
              <Box
                key={item.night ?? "none"}
                sx={(theme) => ({
                  py: "10px",
                  borderBottom: 1,
                  borderColor: theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4",
                  "&:last-of-type": { borderBottom: 0 },
                })}
              >
                <Button
                  size="small"
                  onClick={() => onOpenNight(item.night ?? "none")}
                  sx={{ minWidth: 0, p: 0, fontWeight: 600, justifyContent: "flex-start" }}
                >
                  {label}
                </Button>
                {item.rigs.length > 0 && (
                  <Typography sx={{ display: "block", color: "text.secondary", fontSize: "12px" }}>
                    {item.rigs.join("; ")}
                  </Typography>
                )}
                {item.nightNote && (
                  <Typography sx={{ mt: 0.5, whiteSpace: "pre-wrap", fontSize: "13.5px" }}>
                    {item.nightNote}
                  </Typography>
                )}
                {item.manualNotes.map((session) => (
                  <Typography key={session.id} sx={{ mt: 0.5, whiteSpace: "pre-wrap", fontSize: "13.5px" }}>
                    <Box component="span" sx={{ fontWeight: 600 }}>
                      {filterLabel(session)} {session.exposure_seconds} s:
                    </Box>{" "}
                    {session.notes}
                  </Typography>
                ))}
              </Box>
            );
          })
        )}
      </Box>
    </Box>
  );
}
