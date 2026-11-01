import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";

import type {
  AttemptOutcome,
  ProgressSnapshot,
  SolveAttempt,
} from "@/api/plateSolve";
import { solveColors } from "./solvePalette";
import { stepLabel } from "./solveStepLabels";

const outcomeWords: Record<AttemptOutcome, string> = {
  solved: "Done",
  no_match: "No match",
  skipped: "Skipped",
  step_timeout: "Time limit",
  overall_timeout: "Time limit",
  cancelled: "Cancelled",
  ambiguous: "Ambiguous",
  too_few_stars: "Too few stars",
  error: "Error",
};

interface Row {
  attempt: SolveAttempt;
  state: "done" | "miss" | "searching" | "waiting";
  word: string;
}

interface Props {
  snapshot?: ProgressSnapshot | null;
  attempts?: SolveAttempt[];
}

function completedState(outcome: AttemptOutcome | null): Pick<Row, "state" | "word"> {
  if (outcome === "solved") {
    return { state: "done", word: "Done" };
  }
  if (outcome == null) {
    return { state: "miss", word: "Stopped" };
  }
  if (outcome === "skipped") {
    return { state: "waiting", word: "Skipped" };
  }
  return { state: "miss", word: outcomeWords[outcome] };
}

function attemptDetail(attempt: SolveAttempt): string | null {
  if (attempt.detail) return attempt.detail;
  if (!attempt.ranges.length) return null;
  const ranges = attempt.ranges.map(
    (rangeId) => `${rangeId.replace("-", "°–")}°`,
  );
  return `Fields ${ranges.join(", ")}`;
}

export default function SolveSteps({ snapshot, attempts = [] }: Props) {
  const theme = useTheme();
  const rows: Row[] = [];
  const runningSnapshot = snapshot?.state === "running" ? snapshot : null;

  for (const attempt of snapshot?.attempts ?? attempts) {
    rows.push({ attempt, ...completedState(attempt.outcome) });
  }
  if (runningSnapshot?.active_step) {
    rows.push({
      attempt: runningSnapshot.active_step,
      state: "searching",
      word: "Searching",
    });
  }
  if (runningSnapshot) {
    for (const step of runningSnapshot.planned) {
      rows.push({
        attempt: {
          solver: runningSnapshot.solver,
          step,
          position_source: "none",
          scale_source: "none",
          ranges: [],
          layers: [],
          outcome: null,
          seconds: null,
          detail: null,
        },
        state: "waiting",
        word: "Waiting",
      });
    }
  }
  if (!rows.length) return null;

  const done =
    theme.palette.mode === "dark" ? solveColors.done.dark : solveColors.done.light;
  const miss =
    theme.palette.mode === "dark" ? solveColors.miss.dark : solveColors.miss.light;
  const color = (state: Row["state"]) => {
    if (state === "done") return done;
    if (state === "miss") return miss;
    if (state === "searching") return theme.palette.secondary.main;
    return theme.palette.text.disabled;
  };

  return (
    <Box
      component="ol"
      aria-label="Search steps"
      sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}
    >
      {rows.map(({ attempt, state, word }, index) => {
        const detail = attemptDetail(attempt);
        return (
          <Box
            component="li"
            key={`${attempt.step}-${index}`}
            sx={{
              display: "grid",
              gridTemplateColumns: "20px 1fr auto",
              gap: 1,
              alignItems: "start",
              fontSize: 13,
            }}
          >
            <Box
              aria-hidden
              sx={{
                width: 18,
                height: 18,
                mt: "1px",
                borderRadius: "50%",
                display: "grid",
                placeItems: "center",
                color: state === "done" ? "#0d1f1d" : color(state),
                fontSize: 11,
                fontWeight: 700,
                bgcolor: state === "done" ? done : undefined,
                border:
                  state === "miss"
                    ? `2px solid ${miss}`
                    : state === "searching"
                      ? `2px solid ${theme.palette.secondary.main}`
                      : state === "waiting"
                        ? `2px dashed ${theme.palette.text.disabled}`
                        : undefined,
                borderTopColor: state === "searching" ? "transparent" : undefined,
                animation: state === "searching" ? "solve-spin .9s linear infinite" : undefined,
                "@keyframes solve-spin": { to: { transform: "rotate(360deg)" } },
                "@media (prefers-reduced-motion: reduce)":
                  state === "searching"
                    ? { animation: "none", borderStyle: "dotted" }
                    : undefined,
              }}
            >
              {state === "done" ? "✓" : state === "miss" ? "✕" : ""}
            </Box>
            <Box>
              <Typography sx={{ fontSize: 13 }}>{stepLabel(attempt.step)}</Typography>
              {detail && (
                <Typography color="text.secondary" sx={{ fontSize: 12 }}>
                  {detail}
                </Typography>
              )}
            </Box>
            <Typography
              sx={{
                fontSize: 12,
                color: color(state),
                whiteSpace: "nowrap",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {word}
              {attempt.seconds != null ? ` · ${attempt.seconds.toFixed(1)} s` : ""}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}
