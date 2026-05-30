import { type ReactNode, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import EditIcon from "@mui/icons-material/Edit";
import VisibilityIcon from "@mui/icons-material/Visibility";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  value: string;
  onSave: (next: string) => void;
  placeholder?: string;
  minHeight?: number;
  /** Override the initial view mode (default: rendered). */
  initialMode?: "rendered" | "raw";
  /** Optional content (typically a label) shown to the left of the toggle. */
  label?: ReactNode;
}

/**
 * A reusable Markdown editor with a toggle between a rendered view (default)
 * and a raw-markdown TextField. Calls onSave when the user leaves edit mode
 * with a changed value.
 */
export default function MarkdownEditor({
  value,
  onSave,
  placeholder = "Click to add notes...",
  minHeight = 200,
  initialMode = "rendered",
  label,
}: Props) {
  const [mode, setMode] = useState<"rendered" | "raw">(initialMode);
  const [draft, setDraft] = useState(value);

  // Keep the local draft in sync when the parent value changes externally
  // (e.g. another tab edited it), but only while we're not actively editing.
  useEffect(() => {
    if (mode === "rendered") setDraft(value);
  }, [value, mode]);

  const toEdit = () => {
    setDraft(value);
    setMode("raw");
  };

  const toRendered = () => {
    if (draft !== value) onSave(draft);
    setMode("rendered");
  };

  return (
    <Box>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          minHeight: 32,
          mb: 0.5,
        }}
      >
        <Box>{label}</Box>
        {mode === "rendered" ? (
          <Tooltip title="Edit (markdown)">
            <IconButton size="small" onClick={toEdit} aria-label="Edit markdown">
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        ) : (
          <Tooltip title="Preview">
            <IconButton size="small" onClick={toRendered} aria-label="Preview markdown">
              <VisibilityIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {mode === "raw" ? (
        <TextField
          autoFocus
          fullWidth
          multiline
          minRows={10}
          maxRows={30}
          size="small"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={toRendered}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setDraft(value);
              setMode("rendered");
            }
          }}
          placeholder="Write markdown… **bold**, *italic*, `code`, [link](url), lists, tables…"
        />
      ) : value ? (
        <Box
          onClick={toEdit}
          sx={{
            minHeight,
            p: 2,
            borderRadius: 1,
            cursor: "pointer",
            "&:hover": { bgcolor: "action.hover" },
            // Basic markdown typography — tight but readable, MUI-themed.
            "& p": { my: 1, lineHeight: 1.6 },
            "& h1": { mt: 2, mb: 1, fontSize: "1.5rem", fontWeight: 600 },
            "& h2": { mt: 2, mb: 1, fontSize: "1.25rem", fontWeight: 600 },
            "& h3": { mt: 1.5, mb: 0.5, fontSize: "1.1rem", fontWeight: 600 },
            "& ul, & ol": { my: 1, pl: 3 },
            "& li": { mb: 0.25 },
            "& code": {
              fontFamily: "monospace",
              fontSize: "0.875em",
              bgcolor: "action.hover",
              px: 0.5,
              borderRadius: 0.5,
            },
            "& pre": {
              fontFamily: "monospace",
              fontSize: "0.875em",
              bgcolor: "action.hover",
              p: 1.5,
              borderRadius: 1,
              overflowX: "auto",
            },
            "& pre code": { bgcolor: "transparent", p: 0 },
            "& blockquote": {
              borderLeft: 3,
              borderColor: "divider",
              pl: 1.5,
              my: 1,
              color: "text.secondary",
            },
            "& a": { color: "primary.main" },
            "& table": {
              borderCollapse: "collapse",
              my: 1,
              "& th, & td": { border: 1, borderColor: "divider", px: 1, py: 0.5 },
              "& th": { bgcolor: "action.hover", fontWeight: 600 },
            },
            "& hr": { border: 0, borderTop: 1, borderColor: "divider", my: 2 },
          }}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>
        </Box>
      ) : (
        <Typography
          variant="body2"
          color="text.secondary"
          onClick={toEdit}
          sx={{
            cursor: "pointer",
            minHeight,
            p: 2,
            borderRadius: 1,
            "&:hover": { bgcolor: "action.hover" },
          }}
        >
          {placeholder}
        </Typography>
      )}
    </Box>
  );
}
