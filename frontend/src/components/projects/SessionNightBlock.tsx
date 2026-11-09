import type { ReactNode, Ref } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import type { Filter } from "@/api/equipment";
import type { ProjectSession } from "@/api/projectSessions";
import type { ProjectSetupOption } from "@/api/projects";
import { formatNight } from "@/lib/localDate";
import FilterSwatch from "./FilterSwatch";
import { formatHoursMinutes } from "./IntegrationBars";
import {
  compareFilters,
  resolveSessionFilter,
  summarizeSessionFilters,
} from "./filterColors";
import { setupLabel } from "./setupLabel";

function compareSessions(
  a: ProjectSession,
  b: ProjectSession,
  filtersById: ReadonlyMap<number, Filter>,
): number {
  const filterDifference = compareFilters(
    resolveSessionFilter(a, filtersById),
    resolveSessionFilter(b, filtersById),
  );
  if (filterDifference !== 0) return filterDifference;
  const exposureDifference = a.exposure_seconds - b.exposure_seconds;
  if (exposureDifference !== 0) return exposureDifference;
  return (a.gain ?? Number.POSITIVE_INFINITY) - (b.gain ?? Number.POSITIVE_INFINITY);
}

type CommonSetup = number | null | "mixed" | undefined;

function commonSetup(sessions: ProjectSession[]): CommonSetup {
  if (sessions.length === 0) return undefined;
  const first = sessions[0].rig_setup_id;
  return sessions.every((session) => session.rig_setup_id === first) ? first : "mixed";
}

export interface SessionRigGroup {
  rigId: number | null;
  rigName: string;
  sessions: ProjectSession[];
  setupOptions: ProjectSetupOption[];
}

interface Props {
  sectionRef?: Ref<HTMLElement>;
  headingId: string;
  night: string | null;
  rigGroups: SessionRigGroup[];
  filtersById: ReadonlyMap<number, Filter>;
  nightNote: string | null;
  highlighted: boolean;
  setupPending: boolean;
  onChangeSetup: (sessionId: number, rigSetupId: number | null) => void;
  onEditSession: (session: ProjectSession) => void;
  onDeleteSession: (sessionId: number) => void;
  onEditNote: () => void;
}

export default function SessionNightBlock({
  sectionRef,
  headingId,
  night,
  rigGroups,
  filtersById,
  nightNote,
  highlighted,
  setupPending,
  onChangeSetup,
  onEditSession,
  onDeleteSession,
  onEditNote,
}: Props) {
  const sessions = rigGroups.flatMap((group) => group.sessions);
  const minutes = sessions.reduce((sum, session) => sum + session.integration_minutes, 0);
  const subs = sessions.reduce((sum, session) => sum + session.num_subs, 0);
  const filterMix = summarizeSessionFilters(sessions, filtersById);
  const mixLabel = `Filter mix: ${filterMix
    .map((entry) => `${entry.label} ${formatHoursMinutes(entry.minutes)}`)
    .join(", ")}`;
  const dateLabel = night ? formatNight(night) : "No date";
  const singleRig = rigGroups.length === 1 ? rigGroups[0] : null;

  return (
    <Box
      component="section"
      ref={sectionRef}
      aria-labelledby={headingId}
      sx={(currentTheme) => ({
        bgcolor: "background.paper",
        border: 1,
        borderColor: currentTheme.palette.mode === "dark" ? "#34373d" : "#dcd9d4",
        borderRadius: "8px",
        mb: "10px",
        overflow: "hidden",
        outline: highlighted ? `2px solid ${currentTheme.palette.primary.main}` : "2px solid transparent",
        outlineOffset: "2px",
        animation: highlighted ? "night-focus 2s ease-out forwards" : undefined,
        "@keyframes night-focus": {
          "0%, 75%": { outlineColor: currentTheme.palette.primary.main },
          "100%": { outlineColor: "transparent" },
        },
      })}
    >
      <Box
        sx={(currentTheme) => ({
          display: "grid",
          gridTemplateColumns: "190px minmax(100px, 1fr) auto auto",
          gap: "14px",
          alignItems: "center",
          px: "14px",
          py: "10px",
          borderBottom: 1,
          borderColor: currentTheme.palette.mode === "dark" ? "#34373d" : "#dcd9d4",
          "@media (max-width: 799.95px)": {
            gridTemplateColumns: "minmax(190px, 1fr) auto",
          },
        })}
      >
        <Box>
          <Typography
            id={headingId}
            sx={{ fontSize: "14px", fontWeight: 600, whiteSpace: "nowrap" }}
          >
            {dateLabel}
          </Typography>
          {sessions.length > 0 && (
            <Typography sx={{ color: "text.secondary", fontSize: "12px", whiteSpace: "nowrap" }}>
              {formatHoursMinutes(minutes)}, {subs} sub{subs === 1 ? "" : "s"}
            </Typography>
          )}
        </Box>

        {filterMix.length > 0 ? (
          <Box
            role="img"
            aria-label={mixLabel}
            sx={{
              display: "flex",
              height: "10px",
              gap: "2px",
              borderRadius: "3px",
              overflow: "hidden",
              maxWidth: "360px",
              "@media (max-width: 799.95px)": { gridColumn: "1 / -1" },
            }}
          >
            {filterMix.map((entry) => (
              <Box
                key={entry.key}
                sx={{
                  flex: Math.max(entry.minutes, 0.01),
                  height: "100%",
                  minWidth: 0,
                  borderRadius: "2px",
                  overflow: "hidden",
                }}
              >
                <FilterSwatch
                  filter={entry}
                  width="100%"
                  height="100%"
                  outlineWidth={1.5}
                  display="block"
                />
              </Box>
            ))}
          </Box>
        ) : (
          <Box sx={{ "@media (max-width: 799.95px)": { display: "none" } }} />
        )}

        {singleRig && (
          <RigHeading
            group={singleRig}
            dateLabel={dateLabel}
            setupPending={setupPending}
            onChangeSetup={onChangeSetup}
          />
        )}

        {night && !nightNote && (
          <Button
            size="small"
            onClick={onEditNote}
            aria-label={`Add note for ${dateLabel}`}
            sx={{
              minWidth: 0,
              px: 0,
              whiteSpace: "nowrap",
              justifySelf: "end",
              gridColumn: 4,
              "@media (max-width: 799.95px)": { gridColumn: 2, gridRow: 1 },
            }}
          >
            Add note
          </Button>
        )}

        {nightNote && (
          <Box sx={{ gridColumn: "1 / -1", display: "flex", alignItems: "flex-start", gap: 1 }}>
            <Typography sx={{ flex: 1, whiteSpace: "pre-wrap", fontSize: "13.5px" }}>
              {nightNote}
            </Typography>
            <Button size="small" onClick={onEditNote}>Edit</Button>
          </Box>
        )}
      </Box>

      {rigGroups.length === 0 ? (
        <Typography sx={{ px: "14px", py: "10px", color: "text.secondary", fontSize: "13px" }}>
          No batches left on this night
        </Typography>
      ) : (
        rigGroups.map((group) => (
          <RigSessionRows
            key={group.rigId ?? "none"}
            group={group}
            filtersById={filtersById}
            dateLabel={dateLabel}
            showSubheading={rigGroups.length > 1}
            setupPending={setupPending}
            onChangeSetup={onChangeSetup}
            onEditSession={onEditSession}
            onDeleteSession={onDeleteSession}
          />
        ))
      )}
    </Box>
  );
}

interface RigHeadingProps {
  group: SessionRigGroup;
  dateLabel: string;
  setupPending: boolean;
  onChangeSetup: (sessionId: number, rigSetupId: number | null) => void;
}

function RigHeading({ group, dateLabel, setupPending, onChangeSetup }: RigHeadingProps) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: "14px",
        whiteSpace: "nowrap",
        "@media (max-width: 799.95px)": { gridColumn: "1 / -1" },
      }}
    >
      <Typography sx={{ color: "text.secondary", fontSize: "13px" }}>
        {group.rigName}
      </Typography>
      <SetupControl
        group={group}
        dateLabel={dateLabel}
        setupPending={setupPending}
        onChangeSetup={onChangeSetup}
      />
    </Box>
  );
}

function SetupControl({ group, dateLabel, setupPending, onChangeSetup }: RigHeadingProps) {
  const derived = group.sessions.filter((session) => session.source === "auto");
  const setupBasis = derived.length > 0 ? derived : group.sessions;
  const headingSetup = commonSetup(setupBasis);
  const derivedAnchor = derived[0];
  const selectedOption =
    headingSetup !== undefined && headingSetup !== "mixed"
      ? group.setupOptions.find((option) => option.rig_setup_id === headingSetup)
      : undefined;
  const setupText = headingSetup === "mixed" ? "Mixed" : setupLabel(selectedOption?.until_at);

  if (group.setupOptions.length <= 1) return null;

  if (derivedAnchor) {
    return (
      <TextField
        select
        size="small"
        value={headingSetup === "mixed" ? "mixed" : (headingSetup ?? "")}
        onChange={(event) =>
          onChangeSetup(
            derivedAnchor.id,
            event.target.value === "" ? null : Number(event.target.value),
          )
        }
        disabled={setupPending}
        inputProps={{ "aria-label": `Setup for ${dateLabel}, ${group.rigName}` }}
        SelectProps={{
          displayEmpty: true,
          renderValue: (value) => {
            if (value === "mixed") return "Mixed";
            const setupId = value === "" ? null : Number(value);
            const option = group.setupOptions.find(
              (candidate) => candidate.rig_setup_id === setupId,
            );
            return setupLabel(option?.until_at);
          },
        }}
        sx={(theme) => ({
          minWidth: 150,
          "& .MuiInputBase-root": { height: "28px", borderRadius: "6px", fontSize: "13px" },
          "& .MuiOutlinedInput-notchedOutline": {
            borderColor: theme.palette.mode === "dark" ? "#4a4d54" : "#c4c1bb",
          },
        })}
      >
        {headingSetup === "mixed" && <MenuItem value="mixed" disabled>Mixed</MenuItem>}
        {group.setupOptions.map((setup) => (
          <MenuItem key={setup.rig_setup_id ?? "now"} value={setup.rig_setup_id ?? ""}>
            <Box>
              <Typography sx={{ fontSize: "13px" }}>{setupLabel(setup.until_at)}</Typography>
              <Typography sx={{ color: "text.secondary", fontSize: "11.5px" }}>
                {setup.camera_name}, {setup.image_scale_arcsec_per_pixel.toFixed(2)}″/px
              </Typography>
            </Box>
          </MenuItem>
        ))}
      </TextField>
    );
  }

  return headingSetup !== undefined ? (
    <Typography sx={{ fontSize: "13px", whiteSpace: "nowrap" }}>{setupText}</Typography>
  ) : null;
}

interface RigSessionRowsProps extends RigHeadingProps {
  filtersById: ReadonlyMap<number, Filter>;
  showSubheading: boolean;
  onEditSession: (session: ProjectSession) => void;
  onDeleteSession: (sessionId: number) => void;
}

function RigSessionRows({
  group,
  filtersById,
  dateLabel,
  showSubheading,
  setupPending,
  onChangeSetup,
  onEditSession,
  onDeleteSession,
}: RigSessionRowsProps) {
  const derived = group.sessions.filter((session) => session.source === "auto");
  const setupBasis = derived.length > 0 ? derived : group.sessions;
  const headingSetup = commonSetup(setupBasis);
  const rows = [...group.sessions].sort((a, b) => compareSessions(a, b, filtersById));

  return (
    <Box>
      {showSubheading && (
        <Box
          sx={(currentTheme) => ({
            display: "flex",
            alignItems: "center",
            gap: "14px",
            px: "14px",
            py: "8px",
            borderBottom: 1,
            borderColor: currentTheme.palette.mode === "dark" ? "#34373d" : "#dcd9d4",
          })}
        >
          <Typography sx={{ color: "text.secondary", fontSize: "13px", fontWeight: 600 }}>
            {group.rigName}
          </Typography>
          <SetupControl
            group={group}
            dateLabel={dateLabel}
            setupPending={setupPending}
            onChangeSetup={onChangeSetup}
          />
        </Box>
      )}
      <Box sx={{ overflowX: "auto" }}>
        <Table size="small" sx={{ minWidth: 700, tableLayout: "fixed" }}>
          <TableHead>
            <TableRow>
              <TableCell sx={{ width: "26%" }}>Filter</TableCell>
              <TableCell align="right">Exposure</TableCell>
              <TableCell align="right">Gain</TableCell>
              <TableCell align="right">Subs</TableCell>
              <TableCell>Bin</TableCell>
              <TableCell align="right">Time</TableCell>
              <TableCell sx={{ width: 170 }} />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((session) => {
              const resolvedFilter = resolveSessionFilter(session, filtersById);
              const manual = session.source === "manual";
              const manualSetupDiffers =
                manual &&
                (headingSetup === "mixed" ||
                  (headingSetup !== undefined && session.rig_setup_id !== headingSetup));
              const option = group.setupOptions.find(
                (candidate) => candidate.rig_setup_id === session.rig_setup_id,
              );
              return (
                <TableRow key={session.id}>
                  <TableCell>
                    <Box sx={{ display: "flex", alignItems: "center", gap: "7px", minWidth: 0 }}>
                      <FilterSwatch filter={resolvedFilter} />
                      <Typography component="span" sx={{ fontSize: "13.5px" }}>
                        {resolvedFilter.label}
                      </Typography>
                      {manual && <SmallTag>added by hand</SmallTag>}
                      {manualSetupDiffers && (
                        <SmallTag>{setupLabel(option?.until_at ?? session.setup_until_at)}</SmallTag>
                      )}
                    </Box>
                  </TableCell>
                  <TableCell align="right">{session.exposure_seconds} s</TableCell>
                  <TableCell align="right">{session.gain ?? "—"}</TableCell>
                  <TableCell align="right">{session.num_subs}</TableCell>
                  <TableCell>
                    {session.binning != null ? `${session.binning}×${session.binning}` : "—"}
                  </TableCell>
                  <TableCell align="right">{formatHoursMinutes(session.integration_minutes)}</TableCell>
                  <TableCell align="right">
                    {manual && (
                      <>
                        <Button size="small" onClick={() => onEditSession(session)}>Edit</Button>
                        <Button
                          size="small"
                          onClick={() => onDeleteSession(session.id)}
                          sx={{ color: "text.secondary" }}
                        >
                          Delete
                        </Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Box>
    </Box>
  );
}

function SmallTag({ children }: { children: ReactNode }) {
  return (
    <Box
      component="span"
      sx={(theme) => ({
        display: "inline-flex",
        alignItems: "center",
        height: "18px",
        px: "7px",
        border: 1,
        borderColor: theme.palette.mode === "dark" ? "#4a4d54" : "#c4c1bb",
        borderRadius: "9px",
        color: "text.secondary",
        fontSize: "11px",
        fontWeight: 600,
        whiteSpace: "nowrap",
      })}
    >
      {children}
    </Box>
  );
}
