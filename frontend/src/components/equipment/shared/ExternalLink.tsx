import Box from "@mui/material/Box";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

interface ExternalLinkProps {
  href: string;
  children?: React.ReactNode;
}

/** A styled external link with "opens in new tab" icon. */
export default function ExternalLink({ href, children }: ExternalLinkProps) {
  return (
    <Box
      component="a"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      sx={{
        color: "primary.light",
        textDecoration: "none",
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
        "&:hover": { textDecoration: "underline" },
      }}
    >
      {children ?? href}
      <OpenInNewIcon sx={{ fontSize: 14 }} />
    </Box>
  );
}
