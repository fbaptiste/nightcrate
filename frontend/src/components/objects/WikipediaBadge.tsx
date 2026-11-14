import Box from "@mui/material/Box";

interface Props {
  url: string;
  name: string;
}

export default function WikipediaBadge({ url, name }: Props) {
  return (
    <Box
      component="a"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${name} on Wikipedia (opens in a new tab)`}
      onClick={(event) => event.stopPropagation()}
      sx={{
        flex: "none",
        display: "inline-grid",
        placeItems: "center",
        width: 22,
        height: 22,
        borderRadius: "5px",
        border: 1,
        borderColor: "divider",
        color: "text.primary",
        textDecoration: "none",
        fontFamily: '"Linux Libertine", "Hoefler Text", Georgia, "Times New Roman", serif',
        fontSize: 13,
        lineHeight: 1,
        "&:hover": { borderColor: "primary.main", color: "primary.main" },
      }}
    >
      W
    </Box>
  );
}
