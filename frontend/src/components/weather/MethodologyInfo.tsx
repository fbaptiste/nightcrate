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

const markdownSx = {
  color: "text.secondary",
  fontSize: "0.875rem",
  "& p": { my: 1, lineHeight: 1.6 },
  "& h3": { mt: 2, mb: 0.5, fontSize: "1rem", fontWeight: 600, color: "text.primary" },
  "& ul, & ol": { my: 1, pl: 3 },
  "& li": { mb: 0.25 },
  "& strong": { color: "text.primary" },
  "& blockquote": {
    borderLeft: 3,
    borderColor: "primary.main",
    bgcolor: "action.hover",
    px: 1.5,
    py: 1,
    borderRadius: 1,
    my: 1.5,
    mx: 0,
    "& p": { my: 0 },
  },
  "& table": {
    borderCollapse: "collapse",
    my: 1,
    display: "block",
    overflowX: "auto",
    "& th, & td": { border: 1, borderColor: "divider", px: 1, py: 0.5 },
    "& th": { bgcolor: "action.hover", fontWeight: 600, color: "text.primary", textAlign: "left" },
  },
} as const;

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
            How the verdict works
          </Typography>
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        {methodology.isError ? (
          <Typography variant="body2" color="text.secondary">
            Could not load how the verdict works.
          </Typography>
        ) : (
          <Stack spacing={1}>
            <Typography variant="h6">In one minute</Typography>
            <Box sx={markdownSx}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {methodology.data?.summary ?? ""}
              </ReactMarkdown>
            </Box>
            <Accordion disableGutters elevation={0} variant="outlined">
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle1">The details</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Box sx={markdownSx}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {methodology.data?.details ?? ""}
                  </ReactMarkdown>
                </Box>
              </AccordionDetails>
            </Accordion>
          </Stack>
        )}
      </AccordionDetails>
    </Accordion>
  );
}
