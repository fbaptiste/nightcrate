import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Dialog from "@mui/material/Dialog";
import Typography from "@mui/material/Typography";

import { activateDatabase, fetchAdminStatus, type WorkspaceProblem } from "@/api/admin";
import { SetupWizard } from "@/components/SetupWizard";

const REPO = "https://github.com/fbaptiste/nightcrate";

export function WorkspaceProblemScreen({ problem, currentVersion }: { problem: WorkspaceProblem; currentVersion: string }) {
  return <Box sx={{ minHeight: "100vh", bgcolor: "background.default", display: "grid", placeItems: "center", p: 2 }}><ProblemCard problem={problem} currentVersion={currentVersion} /></Box>;
}

export function WorkspaceProblemDialog({ problem, currentVersion, open, onClose }: { problem: WorkspaceProblem | null; currentVersion: string; open: boolean; onClose: () => void }) {
  if (!problem) return null;
  return <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth><ProblemCard problem={problem} currentVersion={currentVersion} /></Dialog>;
}

function ProblemCard({ problem, currentVersion }: { problem: WorkspaceProblem; currentVersion: string }) {
  const queryClient = useQueryClient();
  const [showWorkspaces, setShowWorkspaces] = useState(false);
  const [create, setCreate] = useState(false);
  const status = useQuery({ queryKey: ["admin-status"], queryFn: fetchAdminStatus });
  if (create) return <SetupWizard />;
  const title = problemTitle(problem, currentVersion);
  const warning = problemWarning(problem);
  const other = status.data?.known_databases.filter((db) => db.path !== problem.workspace_path && db.available) ?? [];
  return <Card sx={{ maxWidth: 600, width: "100%", m: 2 }}><CardContent sx={{ p: 4 }}>
    <Typography variant="h5" sx={{ mb: 2 }}>{title}</Typography>
    {warning && <Box sx={{ p: 2, border: "1px solid", borderColor: problem.kind === "restore_failed" ? "#c07b2b" : "divider", borderRadius: 1.5, mb: 2 }}><Typography>{warning}</Typography></Box>}
    <ProblemActions problem={problem} onOpenOther={() => setShowWorkspaces(true)} />
    {showWorkspaces && <Box sx={{ mt: 2 }}>
      <Typography fontWeight={600} sx={{ mb: 1 }}>Open another workspace</Typography>
      {other.map((db) => <Box key={db.path} sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", py: 0.75 }}><Box><Typography>{db.name}</Typography><Typography variant="caption" color="text.secondary">{db.path}</Typography></Box><Button variant="outlined" onClick={async () => { await activateDatabase(db.path); await queryClient.invalidateQueries({ queryKey: ["health"] }); window.location.reload(); }}>Open</Button></Box>)}
      <Button sx={{ mt: 1 }} onClick={() => setCreate(true)}>Create a new workspace</Button>
    </Box>}
    <Box component="details" sx={{ mt: 2 }}><summary>Details</summary><Typography component="pre" sx={{ whiteSpace: "pre-wrap", fontSize: 12.5 }}>{[problem.error, `Workspace: ${problem.workspace_name}`, problem.backup_path && `${problem.kind === "upgrade_failed" ? "Backup restored from" : "Backup"}: ${problem.backup_path}`].filter(Boolean).join("\n")}</Typography></Box>
  </CardContent></Card>;
}

function problemTitle(problem: WorkspaceProblem, currentVersion: string): string {
  if (problem.kind === "upgrade_failed") return `NightCrate ${currentVersion} couldn't upgrade ${problem.workspace_name}`;
  if (problem.kind === "newer") return problem.last_opened_by ? `${problem.workspace_name} was last opened by NightCrate ${problem.last_opened_by}` : `${problem.workspace_name} was last opened by a newer version of NightCrate`;
  if (problem.kind === "unreadable") return `NightCrate can't read ${problem.workspace_name}'s version information`;
  if (problem.kind === "backup_failed") return `NightCrate couldn't back up ${problem.workspace_name}`;
  return `NightCrate couldn't put ${problem.workspace_name} back as it was`;
}

function problemWarning(problem: WorkspaceProblem): string {
  if (problem.kind === "upgrade_failed") return "Your workspace is unchanged. NightCrate put back the copy it made just before the upgrade.";
  if (problem.kind === "unreadable") return "Nothing was changed.";
  if (problem.kind === "backup_failed") return "Nothing was changed. NightCrate upgrades a workspace only after backing it up.";
  if (problem.kind === "restore_failed") return "The upgrade failed, and so did putting back the copy made before it. Your records are safe in that copy.";
  return "";
}

function ProblemActions({ problem, onOpenOther }: { problem: WorkspaceProblem; onOpenOther: () => void }) {
  if (problem.kind === "newer") return <Box component="ol" sx={{ pl: 2.5 }}><li><a href={`${REPO}/releases/latest`} target="_blank" rel="noopener">Install {problem.last_opened_by ? `${problem.last_opened_by} or newer` : "a newer version"} to open it.</a></li><li>Or <Button variant="text" onClick={onOpenOther}>open another workspace</Button>.</li></Box>;
  if (problem.kind === "backup_failed") return <><Typography>Free some space on the drive that holds this workspace, or check that NightCrate can write to its backups folder, then open NightCrate again.</Typography><Typography>Or <Button onClick={onOpenOther}>open another workspace</Button>.</Typography></>;
  return <Box><Typography fontWeight={600} sx={{ mb: 1 }}>What you can do</Typography><Box component="ol" sx={{ pl: 2.5 }}>
    {problem.kind === "upgrade_failed" && <li>Keep working with the previous version: <a href={problem.last_opened_by ? `${REPO}/releases/tag/v${problem.last_opened_by}` : `${REPO}/releases`} target="_blank" rel="noopener">{problem.last_opened_by ? `download NightCrate ${problem.last_opened_by}` : "download the previous version"}</a> and install it over this one.</li>}
    {problem.kind === "restore_failed" && <><li>Quit NightCrate, then copy {problem.backup_path} over {problem.workspace_path}/nightcrate.db.</li><li>NightCrate will also try again the next time it opens.</li></>}
    <li>Tell us what happened: <a href={`${REPO}/issues/new`} target="_blank" rel="noopener">report it on GitHub</a>.{problem.kind !== "unreadable" && " The details below help."}</li>
    <li>Or <Button onClick={onOpenOther}>open another workspace</Button>.</li>
  </Box></Box>;
}
