import Box from "@mui/material/Box";
import katex from "katex";
import { useMemo } from "react";

// Callers pass hard-coded TeX. KaTeX's default `trust: false` keeps
// \href, \url, and \html* commands from emitting links or attributes.
function renderTex(math: string, displayMode: boolean): string {
  return katex.renderToString(math, { displayMode, throwOnError: false });
}

/** Inline math: renders `$...$`-style LaTeX inside flowing text. */
export function Inline({ children }: { children: string }) {
  const html = useMemo(() => renderTex(children, false), [children]);
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

/** Centered, block-level math display with a little vertical breathing room. */
export function Block({ children }: { children: string }) {
  const html = useMemo(() => renderTex(children, true), [children]);
  return (
    <Box
      sx={{ my: 1.5, overflowX: "auto" }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
