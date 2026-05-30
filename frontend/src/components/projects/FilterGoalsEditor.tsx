import { useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import { LINE_NAMES } from "@/lib/lineNames";
import type { FilterGoal, IntegrationSummary } from "@/api/projectSessions";

interface GoalRow {
  rowId: number;
  line_name: string;
  hours: string;
}

interface Props {
  summary: IntegrationSummary;
  // Bandpass lines covered by the project's rig filters — surfaced first.
  rigLineNames?: Set<string>;
  onCommit: (goals: FilterGoal[]) => void;
}

// Per-filter integration goals. Save-as-you-go: any complete change commits the
// full set (the backend PUT replaces all goals for the project).
export default function FilterGoalsEditor({ summary, rigLineNames, onCommit }: Props) {
  const nextId = useRef(0);
  const [rows, setRows] = useState<GoalRow[]>(() =>
    summary.lines
      .filter((l) => l.goal_minutes != null)
      .map((l) => ({
        rowId: ++nextId.current,
        line_name: l.line_name,
        hours: String(+(l.goal_minutes! / 60).toFixed(2)),
      })),
  );

  const commit = (next: GoalRow[]) => {
    const goals: FilterGoal[] = [];
    const seen = new Set<string>();
    for (const r of next) {
      const h = Number(r.hours);
      if (!r.line_name || r.hours === "" || !(h > 0) || seen.has(r.line_name)) continue;
      seen.add(r.line_name);
      goals.push({ line_name: r.line_name, goal_minutes: h * 60 });
    }
    onCommit(goals);
  };

  // Apply a change to a single row. `doCommit` is set for changes that should
  // persist immediately (line pick, delete); typing in `hours` defers to onBlur.
  const applyRow = (rowId: number, patch: Partial<GoalRow>, doCommit: boolean) => {
    const next = rows.map((r) => (r.rowId === rowId ? { ...r, ...patch } : r));
    setRows(next);
    if (doCommit) commit(next);
  };

  const remove = (rowId: number) => {
    const next = rows.filter((r) => r.rowId !== rowId);
    setRows(next);
    commit(next);
  };

  const addRow = () => {
    setRows([...rows, { rowId: ++nextId.current, line_name: "", hours: "" }]);
  };

  const usedLines = new Set(rows.map((r) => r.line_name).filter(Boolean));

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", mb: 3 }}>
        <Typography variant="h6">Integration goals</Typography>
        <Button
          variant="contained"
          size="small"
          startIcon={<AddIcon />}
          onClick={addRow}
          sx={{ ml: "50px" }}
        >
          Add goal
        </Button>
      </Box>

      <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {rows.map((row) => {
          const eligible = LINE_NAMES.filter(
            (ln) => ln === row.line_name || !usedLines.has(ln),
          );
          const rigEligible = eligible.filter((ln) => rigLineNames?.has(ln) ?? false);
          const otherEligible = eligible.filter((ln) => !(rigLineNames?.has(ln) ?? false));
          return (
          <Box key={row.rowId} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <TextField
              select
              size="small"
              label="Filter"
              value={row.line_name}
              onChange={(e) => applyRow(row.rowId, { line_name: e.target.value }, true)}
              sx={{ width: 180 }}
            >
              {rigEligible.map((ln) => (
                <MenuItem key={`rig:${ln}`} value={ln}>
                  {ln}
                </MenuItem>
              ))}
              {rigEligible.length > 0 && otherEligible.length > 0 && (
                <Divider component="li" key="divider" />
              )}
              {otherEligible.map((ln) => (
                <MenuItem key={`other:${ln}`} value={ln}>
                  {ln}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              label="Goal (hours)"
              type="number"
              value={row.hours}
              onChange={(e) => applyRow(row.rowId, { hours: e.target.value }, false)}
              onBlur={() => commit(rows)}
              inputProps={{ min: 0, step: "any" }}
              sx={{ width: 130 }}
            />
            <IconButton size="small" onClick={() => remove(row.rowId)} aria-label="Remove goal">
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Box>
          );
        })}
      </Box>
    </Box>
  );
}
