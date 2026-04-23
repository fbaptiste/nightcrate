import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

import type { ExternalRef, ExternalRefProvider } from "../../api/dsos";

interface DsoExternalRefsProps {
  refs: ExternalRef[];
  /** Heading text rendered above the link row. Pass an empty string
   *  (or omit via a parent that doesn't want a heading) to suppress —
   *  the planner detail panel uses the surrounding fact-grid layout
   *  as its own labelling and doesn't want a duplicate title. */
  title?: string;
}

/**
 * External-reference section for a DSO detail panel. Renders one
 * hyperlink per visible ref (theme primary, underline on hover) with a
 * trailing ``OpenInNewIcon`` — deliberately NOT as chips so "opens in a
 * new tab" is unambiguous and doesn't get confused with non-clickable
 * designation chips elsewhere in the panel.
 *
 * Wikidata QIDs are stored but intentionally hidden — a QID page is a
 * structured-data view most users won't care about; filtered out below.
 * SIMBAD is inserted for every scored DSO (with designation fallback
 * when Wikidata has no P3083); NED only for extragalactic DSOs where
 * Wikidata has a P2528.
 *
 * Renders nothing when no visible refs survive the allowlist, matching
 * the silent-absence convention used for OpenNGC/NED notes elsewhere in
 * the panel. Provider order comes from the backend
 * (``_EXTERNAL_REF_PROVIDER_ORDER`` in ``api/dso.py``).
 */
const VISIBLE_PROVIDERS: ReadonlySet<ExternalRefProvider> = new Set([
  "wikipedia",
  "simbad",
  "ned",
]);

const PROVIDER_LABEL: Record<ExternalRefProvider, string> = {
  wikipedia: "Wikipedia",
  simbad: "SIMBAD",
  ned: "NED",
  wikidata: "Wikidata",
};

export function DsoExternalRefs({ refs, title = "External references" }: DsoExternalRefsProps) {
  const visible = refs.filter((ref) => VISIBLE_PROVIDERS.has(ref.provider));
  if (visible.length === 0) {
    return null;
  }

  const showTitle = title !== "";
  return (
    <Box>
      {showTitle && (
        <Typography variant="overline" color="text.secondary" id="external-refs-heading">
          {title}
        </Typography>
      )}
      <Stack
        component="ul"
        role="list"
        aria-label={showTitle ? undefined : "External references"}
        aria-labelledby={showTitle ? "external-refs-heading" : undefined}
        direction="row"
        flexWrap="wrap"
        gap={2}
        sx={{ mt: showTitle ? 0.5 : 0, pl: 0, mb: 0, listStyle: "none" }}
      >
        {visible.map((ref) => {
          const prefix = PROVIDER_LABEL[ref.provider];
          const label = ref.label || ref.identifier;
          const ariaLabel = `Open ${prefix} page: ${label} (opens in new tab)`;
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
                {prefix}: {label}
                <OpenInNewIcon sx={{ fontSize: 14 }} />
              </Link>
            </li>
          );
        })}
      </Stack>
    </Box>
  );
}
