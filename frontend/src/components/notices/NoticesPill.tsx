import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Tooltip from "@mui/material/Tooltip";

import type { UpdatesStatus } from "@/api/updates";

const colors = {
  border: { light: "#c07b2b", dark: "#d4993f" },
  fill: { light: "#f6ead9", dark: "#3a3024" },
  text: { light: "#2c2c2c", dark: "#e2e0dd" },
};

function Dot() {
  return <Box component="span" sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: (theme) => colors.border[theme.palette.mode], flex: "0 0 auto" }} />;
}

export function NoticesPill({ status, expanded, onClick }: { status?: UpdatesStatus; expanded: boolean; onClick: (event: React.MouseEvent<HTMLElement>) => void }) {
  const notices = status?.notices ?? [];
  if (notices.length === 0) return null;
  const app = notices.some((notice) => notice.id === "app");
  const label = app ? "Update ready" : `${notices.length} catalog ${notices.length === 1 ? "note" : "notes"}`;
  if (!expanded) {
    return <Tooltip title="Notices" placement="right"><ButtonBase aria-label="Notices" onClick={onClick} sx={{ ml: 0.6, borderRadius: "50%", p: 0.5 }}><Dot /></ButtonBase></Tooltip>;
  }
  return (
    <ButtonBase
      onClick={onClick}
      sx={{
        mt: 1.25, px: "10px", pl: "8px", py: "3px", gap: 0.75,
        border: "1px solid", borderRadius: 999, fontSize: 12.5, fontWeight: 500,
        borderColor: (theme) => colors.border[theme.palette.mode],
        bgcolor: (theme) => colors.fill[theme.palette.mode],
        color: (theme) => colors.text[theme.palette.mode],
      }}
    ><Dot />{label}</ButtonBase>
  );
}
