/**
 * Score breakdown at the bottom of the Planner detail panel (v0.21.0).
 * Final 0-100 chip + per-dimension rows, or gate-failure list when
 * the target didn't score.
 */
import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";

import type {
  DimensionBreakdown,
  PlannerTargetItem,
} from "@/api/planner";
import { ScoreChip } from "./ScoreChip";

interface Props {
  item: PlannerTargetItem;
}

export function ScoreBreakdownSection({ item }: Props) {
  if (item.score_pct === null && !item.score_breakdown) {
    // Anytime mode — no scoring attempted.
    return null;
  }

  const breakdown = item.score_breakdown;
  const gated = item.score_pct === null;

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="overline" color="text.secondary" sx={{ display: "block", mb: 1 }}>
        Score breakdown
      </Typography>

      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 1.5 }}>
        <ScoreChip
          scorePct={item.score_pct}
          qualityLabel={item.quality_label}
          gateFailures={breakdown?.gate_failures}
          size="medium"
        />
        {gated ? (
          <Typography variant="caption" color="text.secondary">
            This target didn&apos;t pass the hard gates for tonight.
          </Typography>
        ) : (
          <Typography variant="caption" color="text.secondary">
            Combined via weighted geometric mean — a weakness in any
            dimension drags the overall score down.
          </Typography>
        )}
      </Stack>

      {gated && breakdown?.gate_failures && (
        <Stack spacing={0.5} sx={{ mb: 1.5, pl: 1 }}>
          {breakdown.gate_failures.map((reason, i) => (
            <Typography key={i} variant="body2" color="text.primary">
              • {reason}
            </Typography>
          ))}
        </Stack>
      )}

      {!gated && breakdown && breakdown.dimensions.length > 0 && (
        <Stack spacing={1.5}>
          {breakdown.dimensions.map((dim) => (
            <DimensionRow key={dim.key} dim={dim} />
          ))}
        </Stack>
      )}
    </Box>
  );
}

function DimensionRow({ dim }: { dim: DimensionBreakdown }) {
  const theme = useTheme();
  const scorePct = Math.round(dim.score * 100);
  const contributionPct = Math.round(dim.contribution * 100);

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="baseline" sx={{ mb: 0.25 }}>
        <Typography variant="body2" fontWeight={500}>
          {dim.label}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          weight {dim.weight.toFixed(1)} · contribution {contributionPct}%
        </Typography>
      </Stack>
      <Stack direction="row" spacing={1} alignItems="center">
        <Box sx={{ flexGrow: 1 }}>
          <LinearProgress
            variant="determinate"
            value={scorePct}
            sx={{
              height: 6,
              borderRadius: 3,
              backgroundColor: theme.palette.action.hover,
              "& .MuiLinearProgress-bar": {
                backgroundColor: theme.palette.primary.main,
              },
            }}
          />
        </Box>
        <Typography
          variant="caption"
          sx={{ minWidth: 32, textAlign: "right", fontVariantNumeric: "tabular-nums" }}
        >
          {scorePct}%
        </Typography>
      </Stack>
      {dim.inputs.length > 0 && (
        <Stack spacing={0.25} sx={{ mt: 0.5, pl: 0.5 }}>
          {dim.inputs.map((line, i) => (
            <Typography key={i} variant="caption" color="text.secondary">
              · {line}
            </Typography>
          ))}
        </Stack>
      )}
    </Box>
  );
}
