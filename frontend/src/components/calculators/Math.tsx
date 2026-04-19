import Box from "@mui/material/Box";
import { InlineMath, BlockMath } from "react-katex";

/** Inline math: renders `$...$`-style LaTeX inside flowing text. */
export function Inline({ children }: { children: string }) {
  return <InlineMath math={children} />;
}

/** Centered, block-level math display with a little vertical breathing room. */
export function Block({ children }: { children: string }) {
  return (
    <Box sx={{ my: 1.5, overflowX: "auto" }}>
      <BlockMath math={children} />
    </Box>
  );
}
