import { useEffect, useRef } from "react";
import Box from "@mui/material/Box";
import { useTheme } from "@mui/material/styles";

const DARK_CSS = `
  body { background: #1a1c20 !important; color: #e2e0dd !important; }
  .swagger-ui,
  .swagger-ui .wrapper { color: #e2e0dd; }
  .swagger-ui .topbar { display: none; }

  /* Info section */
  .swagger-ui .info .title,
  .swagger-ui .info h1, .swagger-ui .info h2,
  .swagger-ui .info h3, .swagger-ui .info h4 { color: #e2e0dd; }
  .swagger-ui .info p, .swagger-ui .info li,
  .swagger-ui .info table td, .swagger-ui .info a { color: #c0beb8; }

  /* Scheme container */
  .swagger-ui .scheme-container { background: #24272c; box-shadow: none; }

  /* Tags (section headers) */
  .swagger-ui .opblock-tag { color: #e2e0dd; border-bottom-color: rgba(255,255,255,0.1); }
  .swagger-ui .opblock-tag small { color: #b0aea8; }
  .swagger-ui .opblock-tag:hover { background: rgba(255,255,255,0.04); }

  /* Operation blocks */
  .swagger-ui .opblock { background: rgba(255,255,255,0.03); border-color: rgba(255,255,255,0.1); }
  .swagger-ui .opblock .opblock-summary { border-color: rgba(255,255,255,0.08); }
  .swagger-ui .opblock .opblock-summary-description { color: #c0beb8; }
  .swagger-ui .opblock .opblock-summary-path,
  .swagger-ui .opblock .opblock-summary-path a { color: #e2e0dd !important; }
  .swagger-ui .opblock .opblock-section-header { background: rgba(255,255,255,0.05); }
  .swagger-ui .opblock .opblock-section-header h4 { color: #e2e0dd; }
  .swagger-ui .opblock .opblock-section-header label { color: #c0beb8; }
  .swagger-ui .opblock-body pre { background: #16181c; color: #e2e0dd; }
  .swagger-ui .opblock-description-wrapper p { color: #c0beb8; }

  /* Parameters */
  .swagger-ui .parameters-col_description p,
  .swagger-ui .parameters-col_description { color: #c0beb8; }
  .swagger-ui .parameter__name { color: #e2e0dd; }
  .swagger-ui .parameter__type { color: #b0aea8; }
  .swagger-ui .parameter__in { color: #b0aea8; }

  /* Responses */
  .swagger-ui .response-col_status { color: #e2e0dd; }
  .swagger-ui .response-col_description,
  .swagger-ui .response-col_description p { color: #c0beb8; }
  .swagger-ui .responses-inner h4,
  .swagger-ui .responses-inner h5 { color: #e2e0dd; }

  /* Tables */
  .swagger-ui table thead tr th,
  .swagger-ui table thead tr td { color: #c0beb8; border-bottom-color: rgba(255,255,255,0.1); }
  .swagger-ui table tbody tr td { color: #e2e0dd; border-bottom-color: rgba(255,255,255,0.06); }

  /* Models */
  .swagger-ui .model-title { color: #e2e0dd; }
  .swagger-ui .model,
  .swagger-ui .model span { color: #c0beb8; }
  .swagger-ui .model .property { color: #e2e0dd; }
  .swagger-ui .prop-type { color: #d4993f; }
  .swagger-ui .prop-format { color: #b0aea8; }

  /* Inputs */
  .swagger-ui input[type=text],
  .swagger-ui textarea,
  .swagger-ui select { background: #16181c; color: #e2e0dd; border-color: rgba(255,255,255,0.2); }

  /* Buttons */
  .swagger-ui .btn { color: #e2e0dd; border-color: rgba(255,255,255,0.25); }
  .swagger-ui .btn:hover { background: rgba(255,255,255,0.08); }
  .swagger-ui .try-out__btn { color: #e2e0dd; border-color: rgba(255,255,255,0.25); }

  /* Dialogs */
  .swagger-ui .dialog-ux .modal-ux { background: #24272c; }
  .swagger-ui .dialog-ux .modal-ux-header h3 { color: #e2e0dd; }

  /* Markdown */
  .swagger-ui .markdown p,
  .swagger-ui .markdown pre,
  .swagger-ui .renderedMarkdown p { color: #c0beb8; }

  /* Loading */
  .swagger-ui .loading-container .loading::after { color: #c0beb8; }

  /* Schemas section — nuke all backgrounds */
  .swagger-ui section.models,
  .swagger-ui section.models *,
  .swagger-ui section.models .model-container,
  .swagger-ui section.models .model-box,
  .swagger-ui section.models button,
  .swagger-ui .model-box-control { background: transparent !important; background-color: transparent !important; }
  .swagger-ui section.models { border-color: rgba(255,255,255,0.1); }
  .swagger-ui section.models h4 { color: #e2e0dd; border-bottom-color: rgba(255,255,255,0.1); }
  .swagger-ui section.models .model-container { margin: 0; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.06); }
  .swagger-ui .model-title { color: #e2e0dd !important; }
  .swagger-ui .model .property.primitive { color: #c0beb8; }
  .swagger-ui .model .star { color: #d4993f; }

  /* Expand/collapse arrows — make them visible */
  .swagger-ui svg.arrow,
  .swagger-ui .expand-operation svg,
  .swagger-ui .model-toggle::after,
  .swagger-ui button svg { fill: #c0beb8 !important; }
  .swagger-ui .expand-methods svg,
  .swagger-ui .expand-operation { fill: #c0beb8 !important; opacity: 1 !important; }
  .swagger-ui svg:not(:root) { fill: #c0beb8; }

  /* Catch-all for remaining text */
  .swagger-ui p, .swagger-ui span, .swagger-ui label,
  .swagger-ui .col_header { color: #c0beb8; }
  .swagger-ui h1, .swagger-ui h2, .swagger-ui h3,
  .swagger-ui h4, .swagger-ui h5, .swagger-ui h6 { color: #e2e0dd; }
`;

const LIGHT_CSS = `
  .swagger-ui .topbar { display: none; }
`;

export function ApiDocsPage() {
  const theme = useTheme();
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const isDark = theme.palette.mode === "dark";

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    function injectTheme() {
      const doc = iframe!.contentDocument;
      if (!doc) return;

      // Remove previous injected style
      const existing = doc.getElementById("nightcrate-theme");
      if (existing) existing.remove();

      const style = doc.createElement("style");
      style.id = "nightcrate-theme";
      style.textContent = isDark ? DARK_CSS : LIGHT_CSS;
      doc.head.appendChild(style);
    }

    iframe.addEventListener("load", injectTheme);
    // Also inject if iframe already loaded (e.g., theme changed)
    if (iframe.contentDocument?.readyState === "complete") {
      injectTheme();
    }

    return () => iframe.removeEventListener("load", injectTheme);
  }, [isDark]);

  return (
    <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column", height: "100%" }}>
      <iframe
        ref={iframeRef}
        src="/docs"
        title="API Documentation"
        style={{
          border: "none",
          flexGrow: 1,
          width: "100%",
          height: "100%",
        }}
      />
    </Box>
  );
}
