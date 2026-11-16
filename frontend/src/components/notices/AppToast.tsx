import { useEffect } from "react";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import SnackbarContent from "@mui/material/SnackbarContent";
import CloseIcon from "@mui/icons-material/Close";

interface Props { message: string | null; linkLabel?: string; linkHref?: string; left: number; onClose: () => void; onShown?: () => void }

export function AppToast({ message, linkLabel, linkHref, left, onClose, onShown }: Props) {
  useEffect(() => { if (message) onShown?.(); }, [message, onShown]);
  return <Snackbar open={Boolean(message)} autoHideDuration={15_000} onClose={onClose} anchorOrigin={{ vertical: "bottom", horizontal: "left" }} sx={{ left: `${left}px !important` }}>
    <SnackbarContent
      message={<>{message} {linkLabel && <Button component="a" href={linkHref} target="_blank" rel="noopener" size="small" sx={{ color: "inherit", textDecoration: "underline" }}>{linkLabel}</Button>}</>}
      action={<IconButton size="small" aria-label="Close" onClick={onClose} sx={{ color: "inherit" }}><CloseIcon fontSize="small" /></IconButton>}
      sx={{ bgcolor: (theme) => theme.palette.mode === "light" ? "#2f3238" : "#e8e5e0", color: (theme) => theme.palette.mode === "light" ? "#ece9e4" : "#23262c" }}
    />
  </Snackbar>;
}
