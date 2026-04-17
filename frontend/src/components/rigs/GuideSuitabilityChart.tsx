import { useEffect, useRef } from "react";
import { useTheme } from "@mui/material/styles";
import { scaleLinear, scaleBand, select, axisBottom } from "d3";
import { ratingColor, type GuideRating } from "@/lib/rigColors";

interface GuideSuitabilityChartProps {
  effectiveErrorMainPixels: number;
  rating: GuideRating | string;
  ratingReason: "ratio" | "scale_cap" | string;
}

const WIDTH = 360;
const HEIGHT = 170;
const MARGIN = { top: 22, right: 24, bottom: 48, left: 90 };

const ROWS = ["Main pixel", "Guide error"] as const;

// Rating-band thresholds on the effective-error-in-main-pixels axis.
const THRESHOLDS: Array<{ x: number; label: string }> = [
  { x: 0.6, label: "Excellent" },
  { x: 1.0, label: "Good" },
  { x: 1.2, label: "Marginal" },
];

export default function GuideSuitabilityChart({
  effectiveErrorMainPixels,
  rating,
  ratingReason,
}: GuideSuitabilityChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const theme = useTheme();

  useEffect(() => {
    const svg = select(svgRef.current);
    svg.selectAll("*").remove();

    const textColor = theme.palette.text.primary;
    const textSecondary = theme.palette.text.secondary;
    const isDark = theme.palette.mode === "dark";
    const mainRef = isDark ? "#555555" : "#bdbdbd";
    const gridColor = isDark ? "#3a3a3a" : "#e0e0e0";

    const innerW = WIDTH - MARGIN.left - MARGIN.right;
    const innerH = HEIGHT - MARGIN.top - MARGIN.bottom;

    const g = svg
      .attr("width", WIDTH)
      .attr("height", HEIGHT)
      .append("g")
      .attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);

    // X domain: go at least to the guide error or 1.5px (past the Marginal line).
    const xMax = Math.max(effectiveErrorMainPixels, 1.5) * 1.1;
    const xScale = scaleLinear().domain([0, xMax]).range([0, innerW]);

    const yScale = scaleBand<string>()
      .domain([...ROWS])
      .range([0, innerH])
      .padding(0.28);

    const bandHeight = yScale.bandwidth();
    const barHeight = bandHeight * 0.65;
    const barOffset = (bandHeight - barHeight) / 2;

    // Threshold vertical dashed lines with labels at the top.
    THRESHOLDS.forEach(({ x, label }) => {
      if (x > xMax) return;
      g.append("line")
        .attr("x1", xScale(x))
        .attr("x2", xScale(x))
        .attr("y1", 0)
        .attr("y2", innerH)
        .attr("stroke", gridColor)
        .attr("stroke-width", 1)
        .attr("stroke-dasharray", "4,3");
      g.append("text")
        .attr("x", xScale(x))
        .attr("y", -7)
        .attr("text-anchor", "middle")
        .attr("fill", textSecondary)
        .attr("font-size", "10px")
        .text(label);
    });

    // Main-pixel reference bar at x=1.0 (always gray).
    const mainY = (yScale("Main pixel") ?? 0) + barOffset;
    g.append("rect")
      .attr("x", 0)
      .attr("y", mainY)
      .attr("width", xScale(1.0))
      .attr("height", barHeight)
      .attr("fill", mainRef)
      .attr("rx", 2);
    g.append("text")
      .attr("x", xScale(1.0) - 6)
      .attr("y", mainY + barHeight / 2)
      .attr("dy", "0.35em")
      .attr("text-anchor", "end")
      .attr("fill", "#ffffff")
      .attr("font-size", "11px")
      .attr("font-weight", 500)
      .text("1.0 px");

    // Guide error bar (color-coded by rating).
    const errorY = (yScale("Guide error") ?? 0) + barOffset;
    const errorBarW = Math.min(xScale(effectiveErrorMainPixels), innerW);
    g.append("rect")
      .attr("x", 0)
      .attr("y", errorY)
      .attr("width", errorBarW)
      .attr("height", barHeight)
      .attr("fill", ratingColor(rating))
      .attr("rx", 2);

    const errorLabel = `${effectiveErrorMainPixels.toFixed(2)} px`;
    const inside = errorBarW > 55;
    g.append("text")
      .attr("x", inside ? errorBarW - 6 : errorBarW + 6)
      .attr("y", errorY + barHeight / 2)
      .attr("dy", "0.35em")
      .attr("text-anchor", inside ? "end" : "start")
      .attr("fill", inside ? "#ffffff" : textColor)
      .attr("font-size", "11px")
      .attr("font-weight", 500)
      .text(errorLabel);

    // If rating was forced by the 6"/pixel scale cap, the bar may not tell
    // the whole story — annotate clearly.
    if (ratingReason === "scale_cap") {
      g.append("text")
        .attr("x", innerW / 2)
        .attr("y", errorY + barHeight + 14)
        .attr("text-anchor", "middle")
        .attr("fill", ratingColor("poor"))
        .attr("font-size", "11px")
        .attr("font-weight", 600)
        .text("Guide scale exceeds 6\u2033/pixel hard cap");
    }

    // X axis
    const xAxis = axisBottom(xScale)
      .ticks(5)
      .tickFormat((d) => `${d} px`);
    const xAxisG = g
      .append("g")
      .attr("transform", `translate(0,${innerH})`)
      .call(xAxis);
    xAxisG
      .selectAll(".tick text")
      .attr("fill", textColor)
      .attr("font-size", "11px")
      .style("fill", textColor);
    xAxisG.selectAll(".domain, .tick line").attr("stroke", textSecondary);

    g.append("text")
      .attr("x", innerW / 2)
      .attr("y", innerH + 38)
      .attr("text-anchor", "middle")
      .attr("fill", textColor)
      .attr("font-size", "12px")
      .text("Main-camera pixels");

    // Y labels (manual)
    ROWS.forEach((label) => {
      g.append("text")
        .attr("x", -8)
        .attr("y", (yScale(label) ?? 0) + bandHeight / 2)
        .attr("dy", "0.35em")
        .attr("text-anchor", "end")
        .attr("fill", textColor)
        .attr("font-size", "12px")
        .text(label);
    });
  }, [effectiveErrorMainPixels, rating, ratingReason, theme]);

  return <svg ref={svgRef} />;
}
