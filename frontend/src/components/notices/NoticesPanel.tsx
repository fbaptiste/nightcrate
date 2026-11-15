import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import { useNavigate } from "react-router-dom";

import type { NoticeAction, UpdateNotice, UpdatesStatus } from "@/api/updates";
import { noticeDescription, noticeTitle } from "./noticeText";

interface Props {
  anchorEl: HTMLElement | null;
  status?: UpdatesStatus;
  onClose: () => void;
  onDismiss: (id: UpdateNotice["id"], action: NoticeAction) => void;
  onInstall: (notice: UpdateNotice) => void;
}

export function NoticesPanel({ anchorEl, status, onClose, onDismiss, onInstall }: Props) {
  const navigate = useNavigate();
  const openCatalogs = () => { onClose(); navigate("/admin#catalogs"); };
  return (
    <Popover
      open={Boolean(anchorEl)} anchorEl={anchorEl} onClose={onClose}
      anchorOrigin={{ vertical: "top", horizontal: "right" }}
      transformOrigin={{ vertical: "top", horizontal: "left" }}
      slotProps={{ paper: { sx: { ml: 1, width: 430, maxWidth: "calc(100vw - 24px)", border: "1px solid", borderColor: (theme) => theme.palette.mode === "light" ? "rgba(0,0,0,0.15)" : "rgba(255,255,255,0.13)", borderRadius: "10px", boxShadow: (theme) => theme.palette.mode === "light" ? "0 10px 32px rgba(0,0,0,0.16)" : "0 12px 36px rgba(0,0,0,0.5)" } } }}
    >
      <Box sx={{ px: 2.25, py: 1.25, display: "flex", alignItems: "center" }}>
        <Typography sx={{ fontSize: 15, fontWeight: 600, flex: 1 }}>Notices</Typography>
        <IconButton size="small" aria-label="Close" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
      </Box>
      <Divider />
      {(status?.notices ?? []).map((notice, index) => (
        <Box key={notice.id}>
          {index > 0 && <Divider />}
          <Box sx={{ px: 2.25, py: "14px", pb: 2, borderLeft: notice.id === "app" ? "3px solid" : 0, borderLeftColor: notice.id === "app" ? (theme) => theme.palette.mode === "light" ? "#f6ead9" : "#3a3024" : undefined }}>
            <Typography sx={{ fontSize: 14.5, fontWeight: 600 }}>{noticeTitle(notice)}</Typography>
            <Typography color="text.secondary" sx={{ fontSize: 13, mt: 0.5 }}>{noticeDescription(notice)}</Typography>
            {notice.id === "app" && <AppNoticeBody notice={notice} installKind={status!.install_kind} onInstall={() => onInstall(notice)} onDismiss={onDismiss} />}
            {notice.id !== "app" && (
              <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 1.25 }}>
                <Button variant="outlined" size="small" onClick={openCatalogs}>Open Catalogs</Button>
                {notice.id === "openngc"
                  ? <Button size="small" color="inherit" onClick={() => onDismiss(notice.id, "skip")}>Skip this release</Button>
                  : <Button size="small" color="inherit" onClick={() => onDismiss(notice.id, "remind")}>Remind me in 6 months</Button>}
              </Box>
            )}
          </Box>
        </Box>
      ))}
    </Popover>
  );
}

function AppNoticeBody({ notice, installKind, onInstall, onDismiss }: { notice: UpdateNotice; installKind: UpdatesStatus["install_kind"]; onInstall: () => void; onDismiss: Props["onDismiss"] }) {
  return <>
    {notice.notes.length > 0 && <Box component="ul" sx={{ pl: 2.5, my: 1, fontSize: 13 }}>{notice.notes.map((note) => <li key={note}>{note}</li>)}</Box>}
    {notice.release_url && <Typography component="a" href={notice.release_url} target="_blank" rel="noopener" sx={{ fontSize: 13 }}>All release notes on GitHub</Typography>}
    {installKind === "source" ? (
      <>
        <Typography color="text.secondary" sx={{ fontSize: 12.5, mt: 1.25 }}>You're running NightCrate from source code. To update, pull the latest version from GitHub.</Typography>
        <Box sx={{ display: "flex", gap: 0.5, mt: 1 }}>
          <Button size="small" color="inherit" onClick={() => onDismiss("app", "later")}>Later</Button>
          <Button size="small" color="inherit" onClick={() => onDismiss("app", "skip")}>Skip this version</Button>
        </Box>
      </>
    ) : <>
      <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 1.25 }}>
        {notice.installable
          ? <Button variant="contained" size="small" onClick={onInstall}>Install and restart</Button>
          : <Button variant="outlined" size="small" component="a" href={notice.release_url ?? undefined} target="_blank" rel="noopener">Download the installer</Button>}
        <Button size="small" color="inherit" onClick={() => onDismiss("app", "later")}>Later</Button>
        <Button size="small" color="inherit" onClick={() => onDismiss("app", "skip")}>Skip this version</Button>
      </Box>
      <Typography color="text.secondary" sx={{ fontSize: 12.5, mt: 1 }}>NightCrate backs up your workspace before it upgrades it. Installing takes about a minute, and NightCrate opens again by itself.</Typography>
    </>}
  </>;
}
