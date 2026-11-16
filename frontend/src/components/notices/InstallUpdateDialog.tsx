import { useCallback, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import LinearProgress from "@mui/material/LinearProgress";
import Typography from "@mui/material/Typography";

import { releaseInstall, reserveInstall, type RunningActivity } from "@/api/app";
import type { UpdateNotice } from "@/api/updates";
import { installUpdate, isDesktopShell, type InstallFailure, type InstallProgress } from "@/lib/desktopShell";
import { isAnalyzeRunActive } from "@/lib/useAnalyzeRun";

type DialogState =
  | { kind: "busy"; running: RunningActivity[] }
  | { kind: "already" }
  | { kind: "progress"; notice: UpdateNotice; progress: InstallProgress }
  | { kind: "failure"; notice: UpdateNotice; failure: InstallFailure };

export function useInstallFlow() {
  const [state, setState] = useState<DialogState | null>(null);
  const start = useCallback(async (notice: UpdateNotice): Promise<boolean> => {
    if (isAnalyzeRunActive()) {
      setState({ kind: "busy", running: [{ kind: "frame_analysis", label: "" }] });
      return false;
    }
    const reservation = await reserveInstall();
    if ("running" in reservation) {
      setState({ kind: "busy", running: reservation.running });
      return false;
    }
    if ("installInProgress" in reservation) {
      setState({ kind: "already" });
      return false;
    }
    if (!isDesktopShell()) {
      await releaseInstall(reservation.token);
      setState({ kind: "failure", notice, failure: { stage: "busy", message: "The desktop update bridge is unavailable." } });
      return false;
    }
    setState({ kind: "progress", notice, progress: { stage: "downloading", downloaded: 0 } });
    try {
      await installUpdate(notice.version!, reservation.token, (progress) => {
        setState({ kind: "progress", notice, progress });
      });
      return true;
    } catch (error) {
      const failure = error as InstallFailure;
      if (failure.stage === "busy") {
        await releaseInstall(reservation.token);
        setState({ kind: "already" });
        return false;
      }
      setState({ kind: "failure", notice, failure });
      return false;
    }
  }, []);
  return { start, installing: state?.kind === "progress", dialog: <InstallDialog state={state} onClose={() => setState(null)} /> };
}

function busyCopy(running: RunningActivity[]): { title: string; body: React.ReactNode } {
  if (running.length > 1) return { title: "Install after this work finishes", body: <Box component="ul">{running.map((item, i) => <li key={`${item.kind}-${i}`}>{activityLabel(item)}</li>)}</Box> };
  const item = running[0];
  if (item?.kind === "scan") return { title: "Install after the scan finishes", body: <>NightCrate is scanning a folder for <b>{item.label}</b>. Click Install and restart again once it has finished.</> };
  const label = item ? activityLabel(item) : "work";
  return { title: `Install after the ${label} finishes`, body: `Click Install and restart again once it has finished.` };
}

function activityLabel(item: RunningActivity): string {
  if (item.kind === "frame_analysis") return "frame analysis";
  if (item.kind === "plate_solve") return "plate solve";
  if (item.kind === "catalog") return item.label ? `catalog update (updating ${item.label})` : "catalog update";
  if (item.kind === "star_catalog") return "star catalog download";
  return item.label ? `scan for ${item.label}` : "scan";
}

// The plan intentionally keeps the install-flow hook beside its private dialog.
// eslint-disable-next-line react-refresh/only-export-components
function InstallDialog({ state, onClose }: { state: DialogState | null; onClose: () => void }) {
  if (!state) return null;
  if (state.kind === "busy") {
    const copy = busyCopy(state.running);
    return <Dialog open><DialogTitle>{copy.title}</DialogTitle><DialogContent><Typography component="div">{copy.body}</Typography></DialogContent><DialogActions><Button variant="contained" onClick={onClose}>OK</Button></DialogActions></Dialog>;
  }
  if (state.kind === "already") return <Dialog open><DialogTitle>An update is already being installed.</DialogTitle><DialogActions><Button variant="contained" onClick={onClose}>OK</Button></DialogActions></Dialog>;
  if (state.kind === "failure") {
    const { notice, failure } = state;
    const message = failure.stage === "busy"
      ? failure.message
      : failure.stage === "download"
        ? `NightCrate couldn't download ${notice.version}: ${failure.message}. Nothing has changed.`
        : `NightCrate couldn't install ${notice.version} and is still on ${notice.current_version}.`;
    return <Dialog open><DialogTitle>Update failed</DialogTitle><DialogContent><Typography>{message}</Typography></DialogContent><DialogActions><Button component="a" href={notice.release_url ?? undefined} target="_blank" rel="noopener">Download the installer</Button><Button onClick={onClose}>Close</Button></DialogActions></Dialog>;
  }
  const { notice, progress } = state;
  const bytes = progress.downloaded ?? 0;
  const total = progress.total;
  const mb = total ? `${Math.ceil(total / 1_000_000)} MB` : bytes ? `${Math.ceil(bytes / 1_000_000)} MB` : "";
  const downloading = progress.stage === "downloading";
  return <Dialog open disableEscapeKeyDown><DialogTitle>Installing NightCrate {notice.version}</DialogTitle><DialogContent sx={{ minWidth: 390 }}>
    <Box component="ol" sx={{ pl: 2.5, m: 0, "& li": { py: 1, borderTop: 1, borderColor: "divider" } }}>
      <li><Box sx={{ display: "flex", justifyContent: "space-between" }}><span>Download the update</span><span>{mb}</span></Box>{downloading && <LinearProgress variant={total ? "determinate" : "indeterminate"} value={total ? bytes / total * 100 : undefined} sx={{ mt: 0.75 }} />}</li>
      <li>Install it{progress.stage === "installing" && <LinearProgress sx={{ mt: 0.75 }} />}</li>
      <li>Open NightCrate again</li>
      <li>Back up and upgrade your workspace</li>
    </Box>
  </DialogContent></Dialog>;
}
