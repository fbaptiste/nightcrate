import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";

import { checkForUpdates, clearSkippedVersion, fetchUpdates, setCheckAutomatically } from "@/api/updates";
import { formatCheckTime } from "@/components/notices/noticeText";

export function UpdatesAdminSection() {
  const queryClient = useQueryClient();
  const [checking, setChecking] = useState(false);
  const query = useQuery({ queryKey: ["updates"], queryFn: fetchUpdates });
  const status = query.data;
  const setData = (value: Awaited<ReturnType<typeof fetchUpdates>>) => queryClient.setQueryData(["updates"], value);
  const result = !status?.last_attempt_at
    ? "NightCrate hasn't checked yet."
    : status.last_error
      ? `Last check failed ${formatCheckTime(status.last_attempt_at)}: ${status.last_error}.`
      : `Last checked ${formatCheckTime(status.last_attempt_at)}. ${status.notices.some((item) => item.id === "app") ? `NightCrate ${status.notices.find((item) => item.id === "app")?.version} is available.` : "You have the latest version."}`;
  return <>
    <Typography variant="h6" sx={{ mb: 1 }}>Updates</Typography>
    <Paper sx={{ mb: 3 }}>
      <Row title={`NightCrate ${status?.current_version ?? "…"}`} description={result}>
        <Button variant="outlined" disabled={checking} onClick={async () => { setChecking(true); try { setData(await checkForUpdates()); } finally { setChecking(false); } }}>{checking ? <CircularProgress size={18} /> : "Check now"}</Button>
      </Row>
      <Divider />
      <Row title="Check for new versions automatically" description="Once a day, NightCrate asks GitHub whether a newer version of NightCrate or of the OpenNGC catalog exists.">
        <Switch aria-label="Check for new versions automatically" checked={status?.check_automatically === true} onChange={async (event) => setData(await setCheckAutomatically(event.target.checked))} />
      </Row>
      {status?.skipped_version && <><Divider /><Row title={`You skipped ${status.skipped_version}`} description="NightCrate won't mention it again unless you ask."><Button onClick={async () => { await clearSkippedVersion(); await query.refetch(); }}>Show it again</Button></Row></>}
      {status?.install_kind === "source" && <Box sx={{ mx: 2, mb: 2, p: 1.5, bgcolor: "background.default", borderRadius: 1 }}><Typography variant="body2">Running from source code, so NightCrate can't install updates itself. To update, pull the latest version from GitHub.</Typography></Box>}
    </Paper>
  </>;
}

function Row({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return <Box sx={{ display: "flex", gap: 2, alignItems: "center", justifyContent: "space-between", px: 2, py: 1.5 }}><Box><Typography fontWeight={500}>{title}</Typography><Typography variant="body2" color="text.secondary">{description}</Typography></Box>{children}</Box>;
}
