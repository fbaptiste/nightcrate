import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";

interface Props {
  name: string;
  otherNames: string[];
  children?: ReactNode;
  title?: string;
  tabIndex?: number | null;
}

export default function NameWithAlternates({
  name,
  otherNames,
  children,
  title,
  tabIndex = 0,
}: Props) {
  const content = children ?? name;
  const tooltipTitle = title ?? (otherNames.length > 0 ? `Also known as ${otherNames.join(", ")}` : null);
  if (!tooltipTitle) return <>{content}</>;

  return (
    <Tooltip title={tooltipTitle}>
      <Box component="span" tabIndex={tabIndex ?? undefined} sx={{ display: "inline" }}>
        {content}
      </Box>
    </Tooltip>
  );
}
