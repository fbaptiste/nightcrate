import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

import type { ExternalRef } from "../../api/dsos";

interface DsoExternalRefsProps {
  refs: ExternalRef[];
  title?: string;
}

/**
 * External-reference section for a DSO detail panel. Renders each
 * Wikipedia ref as a plain hyperlink (theme primary, underline on
 * hover) with a trailing ``OpenInNewIcon`` — deliberately NOT as a
 * chip so "opens in a new tab" is unambiguous visually and doesn't
 * get confused with non-clickable designation chips elsewhere in the
 * panel.
 *
 * Wikidata QIDs are stored alongside each Wikipedia entry (for
 * future features — Commons image pulls, NED cross-lookup) but are
 * not rendered in the MVP UI. Renders nothing when there are no
 * Wikipedia refs, matching the silent-absence convention used for
 * OpenNGC/NED notes elsewhere in the panel.
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
        gap={2}
        sx={{ mt: 0.5, pl: 0, mb: 0, listStyle: "none" }}
      >
        {wikipedia.map((ref) => {
          const label = ref.label || ref.identifier;
          const ariaLabel = `Open Wikipedia article: ${label} (opens in new tab)`;
          return (
            <li key={`${ref.provider}-${ref.language ?? ""}-${ref.identifier}`}>
              <Link
                href={ref.url ?? undefined}
                target="_blank"
                rel="noopener noreferrer"
                underline="hover"
                aria-label={ariaLabel}
                sx={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 0.5,
                  fontSize: "0.85rem",
                  fontWeight: 500,
                }}
              >
                Wikipedia: {label}
                <OpenInNewIcon sx={{ fontSize: 14 }} />
              </Link>
            </li>
          );
        })}
      </Stack>
    </Box>
  );
}
