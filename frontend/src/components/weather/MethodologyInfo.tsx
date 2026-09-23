import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Stack from "@mui/material/Stack";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import InfoIcon from "@mui/icons-material/Info";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { fetchMethodology } from "@/api/weather";

/**
 * "How are scores calculated?" — rendered from the backend's own METHODOLOGY
 * text.
 *
 * This component used to hardcode its own copy of the factor table, the label
 * ranges and the scoring prose. That duplicate silently went stale every time
 * the model changed — it was still describing cloud gating and a 35% sky-clarity
 * weight after the v0.41.4 redesign removed both. The endpoint already existed
 * and `fetchMethodology` was already written; it just was not wired up. One
 * source of truth now: change the model, change `api/weather.py:METHODOLOGY`,
 * and this follows.
 */
export default function MethodologyInfo() {
  const methodology = useQuery({
    queryKey: ["weather-methodology"],
    queryFn: fetchMethodology,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  return (
    <Accordion
      disableGutters
      elevation={0}
      sx={{
        maxWidth: 720,
        background: "transparent",
        "&::before": { display: "none" },
      }}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        sx={{ "& .MuiAccordionSummary-content": { flexGrow: 0 } }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <InfoIcon fontSize="small" color="action" />
          <Typography variant="body2" color="text.secondary">
            How are scores calculated?
          </Typography>
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        {methodology.isError ? (
          <Typography variant="body2" color="text.secondary">
            Could not load the scoring methodology.
          </Typography>
        ) : (
          <Box
            sx={{
              color: "text.secondary",
              fontSize: "0.875rem",
              // Markdown typography, matching MarkdownEditor's conventions.
              "& p": { my: 1, lineHeight: 1.6 },
              "& h3": { mt: 2, mb: 0.5, fontSize: "1rem", fontWeight: 600, color: "text.primary" },
              "& ul, & ol": { my: 1, pl: 3 },
              "& li": { mb: 0.25 },
              "& strong": { color: "text.primary" },
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
              "& a": { color: "primary.main" },
              // The tables are wide; let them scroll rather than push the page.
              "& table": {
                borderCollapse: "collapse",
                my: 1,
                display: "block",
                overflowX: "auto",
                "& th, & td": { border: 1, borderColor: "divider", px: 1, py: 0.5 },
                "& th": { bgcolor: "action.hover", fontWeight: 600, color: "text.primary" },
              },
            }}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {methodology.data?.text ?? ""}
            </ReactMarkdown>
          </Box>
        )}
      </AccordionDetails>
    </Accordion>
  );
}
