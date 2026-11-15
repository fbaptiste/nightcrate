import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import CloseIcon from "@mui/icons-material/Close";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";

interface Props {
  id: number;
  message: string | null;
  left: number;
  onClose: () => void;
}

export function WandToast({ id, message, left, onClose }: Props) {
  return (
    <Snackbar
      key={id}
      open={message !== null}
      autoHideDuration={15_000}
      onClose={(_event, reason) => {
        if (reason !== "clickaway") onClose();
      }}
      anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      message={
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5 }}>
          <AutoFixHighIcon sx={{ color: "primary.main", fontSize: 16, mt: "2px" }} />
          <Box component="span">{message}</Box>
        </Box>
      }
      action={
        <IconButton size="small" color="inherit" onClick={onClose} aria-label="Close">
          <CloseIcon sx={{ fontSize: 18 }} />
        </IconButton>
      }
      sx={{
        left: `${left}px !important`,
        right: "auto !important",
        "& .MuiSnackbarContent-root": {
          maxWidth: 460,
          flexWrap: "nowrap",
          alignItems: "flex-start",
        },
        "& .MuiSnackbarContent-message": {
          minWidth: 0,
          flex: "1 1 auto",
        },
        "& .MuiSnackbarContent-action": {
          flex: "0 0 auto",
          alignSelf: "flex-start",
          m: 0,
          ml: 1,
          p: 0,
        },
      }}
    />
  );
}
