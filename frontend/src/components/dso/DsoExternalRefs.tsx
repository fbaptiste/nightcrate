import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { ExternalRef } from "../../api/dsos";

interface DsoExternalRefsProps {
  refs: ExternalRef[];
  title?: string;
}

/**
 * External-reference chips for a DSO. Surfaces Wikipedia links via
 * Wikidata. Wikidata QIDs are stored alongside each Wikipedia entry for
 * future features (automated enrichment, NED cross-lookup) but are not
 * rendered in the MVP UI — chips stay focused on user-facing resources.
 *
 * Renders nothing when there are no Wikipedia refs, matching the
 * silent-absence convention used for OpenNGC/NED notes elsewhere in the
 * detail panel.
 */
export function DsoExternalRefs({ refs, title = "External references" }: DsoExternalRefsProps) {
  const wikipedia = refs.filter((ref) => ref.provider === "wikipedia");
  if (wikipedia.length === 0) {
    return null;
  }

  return (
    <Box>
      <Typography variant="overline" color="text.secondary" id="external-refs-heading">
        {title}
      </Typography>
      <Stack
        component="ul"
        role="list"
        aria-labelledby="external-refs-heading"
        direction="row"
        flexWrap="wrap"
        gap={1}
        sx={{ mt: 1, pl: 0, mb: 0, listStyle: "none" }}
      >
        {wikipedia.map((ref) => {
          const label = ref.label || ref.identifier;
          const displayLabel = `Wikipedia · ${label}`;
          const ariaLabel = `Open Wikipedia article: ${label} (opens in new tab)`;
          return (
            <li key={`${ref.provider}-${ref.language ?? ""}-${ref.identifier}`}>
              <Chip
                component="a"
                clickable
                href={ref.url ?? undefined}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={ariaLabel}
                label={displayLabel}
                size="small"
                variant="outlined"
              />
            </li>
          );
        })}
      </Stack>
    </Box>
  );
}
