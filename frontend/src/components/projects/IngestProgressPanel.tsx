import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import type { IngestProgress } from "@/api/projectCatalog";

const STAGE_LABELS: Record<IngestProgress["stage"], string> = {
  listing: "Listing files",
  reading: "Reading file headers",
  saving: "Saving",
  grouping: "Grouping into sessions",
};

function folderName(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

export default function IngestProgressPanel({
  progress,
}: {
  progress: IngestProgress;
}) {
  const percent = progress.total > 0
    ? Math.min(100, (progress.done / progress.total) * 100)
    : 0;

  return (
    <Box
      role="status"
      aria-live="polite"
      sx={{
        border: 1,
        borderColor: "divider",
        borderRadius: "8px",
        bgcolor: "background.paper",
        p: 2,
        minWidth: 0,
      }}
    >
      <Tooltip title={progress.folder ?? ""} arrow>
        <Typography
          component="h3"
          sx={{ fontSize: 15, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        >
          {progress.folder ? folderName(progress.folder) : "Scanning files"}
        </Typography>
      </Tooltip>
      <Typography sx={{ mt: 0.5, color: "text.secondary", fontSize: 13 }}>
        {STAGE_LABELS[progress.stage]}
      </Typography>

      {progress.stage === "reading" && (
        <Box sx={{ mt: 1.5 }}>
          <Typography sx={{ mb: 0.75, color: "text.secondary", fontSize: 13, fontVariantNumeric: "tabular-nums" }}>
            {progress.done.toLocaleString()} of {progress.total.toLocaleString()} files
          </Typography>
          <LinearProgress
            variant="determinate"
            value={percent}
            aria-label={`${progress.done} of ${progress.total} files read`}
          />
        </Box>
      )}

      <Box
        sx={{
          mt: 1.5,
          height: 220,
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-end",
          overflow: "hidden",
          borderRadius: "4px",
          bgcolor: "action.hover",
          px: 1,
        }}
      >
        {progress.recent.map((entry, index) => (
          <Typography
            key={`${index}:${entry.path}`}
            title={entry.path}
            noWrap
            sx={{
              flex: "0 0 22px",
              minWidth: 0,
              overflow: "hidden",
              textOverflow: "ellipsis",
              color: entry.ok ? "text.secondary" : "warning.main",
              fontFamily: "monospace",
              fontSize: 12,
              lineHeight: "22px",
            }}
          >
            {entry.path}
            {!entry.ok && <> {"— couldn't be read"}</>}
          </Typography>
        ))}
      </Box>
    </Box>
  );
}
