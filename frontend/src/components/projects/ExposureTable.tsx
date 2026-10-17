import Box from "@mui/material/Box";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { ExposureLine } from "@/api/projectSessions";
import { formatHoursMinutes } from "./IntegrationBars";

interface Props {
  lines: ExposureLine[];
}

// Captured subs per filter and exposure, below the integration bars. Captured,
// not accepted: which subs a stack kept is the processing software's business.
export default function ExposureTable({ lines }: Props) {
  return (
    <Box sx={{ maxWidth: 560 }}>
      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
        Captured subs by filter and exposure
      </Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Filter</TableCell>
            <TableCell align="right">Exp (s)</TableCell>
            <TableCell align="right">Subs</TableCell>
            <TableCell align="right">Time</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {lines.map((line) => (
            <TableRow key={`${line.label}|${line.exposure_seconds}`} hover>
              <TableCell sx={{ maxWidth: 200 }}>
                {/* A free string, possibly a long FITS filter name — truncate like
                    the bars rather than wrap. */}
                <Tooltip title={line.label}>
                  <Box
                    component="span"
                    sx={{
                      display: "inline-block",
                      maxWidth: "100%",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      verticalAlign: "bottom",
                    }}
                  >
                    {line.label}
                  </Box>
                </Tooltip>
              </TableCell>
              <TableCell align="right">{line.exposure_seconds}</TableCell>
              <TableCell align="right">{line.sub_count}</TableCell>
              <TableCell align="right">{formatHoursMinutes(line.actual_minutes)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
