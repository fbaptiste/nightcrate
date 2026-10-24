import Box from "@mui/material/Box";
import katex from "katex";
import { useMemo } from "react";

type Rendered = { html: string } | { error: string };

// Callers pass hard-coded TeX. KaTeX's default `trust: false` keeps \href,
// \url, \includegraphics, and \html* commands from emitting links, images,
// or attributes.
function renderTex(math: string, displayMode: boolean): Rendered {
  try {
    return {
      html: katex.renderToString(math, { displayMode, throwOnError: false }),
    };
  } catch (error) {
    // Like react-katex, show the message instead of failing the whole page.
    if (error instanceof katex.ParseError || error instanceof TypeError) {
      return { error: error.message };
    }
    throw error;
  }
}

/** Inline math: renders `$...$`-style LaTeX inside flowing text. */
export function Inline({ children }: { children: string }) {
  const rendered = useMemo(() => renderTex(children, false), [children]);
  if ("error" in rendered) return <span>{rendered.error}</span>;
  return <span dangerouslySetInnerHTML={{ __html: rendered.html }} />;
}

/** Centered, block-level math display with a little vertical breathing room. */
export function Block({ children }: { children: string }) {
  const rendered = useMemo(() => renderTex(children, true), [children]);
  if ("error" in rendered) {
    return <Box sx={{ my: 1.5 }}>{rendered.error}</Box>;
  }
  return (
    <Box
      sx={{ my: 1.5, overflowX: "auto" }}
      dangerouslySetInnerHTML={{ __html: rendered.html }}
    />
  );
}
