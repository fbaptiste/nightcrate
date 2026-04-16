import { useEffect, useRef } from "react";
import { scaleLinear, scaleBand, select, axisBottom } from "d3";

interface SamplingChartProps {
  imageScale: number; // unbinned arcsec/pixel
  idealRangeLow: number; // arcsec/pixel
  idealRangeHigh: number; // arcsec/pixel
  binningRecommendations: Record<number, string>; // {1: "oversampled", 2: "well_sampled", ...}
}

const WIDTH = 360;
const HEIGHT = 190;
const MARGIN = { top: 22, right: 20, bottom: 48, left: 55 };

const BLUE = "#1976d2";    // well sampled
const ORANGE = "#ed6c02";  // oversampled (too fine, wasting SNR)
const TEAL = "#00695c";    // undersampled (too coarse, blocky stars)
const IDEAL_ZONE_FILL = "#e3f2fd";
const TEXT_COLOR = "#111111";

const BINNING_LABELS = ["1\u00d71", "2\u00d72", "3\u00d73", "4\u00d74"];
const BINNING_LEVELS = [1, 2, 3, 4];

export default function SamplingChart({
  imageScale,
  idealRangeLow,
  idealRangeHigh,
  binningRecommendations,
}: SamplingChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = select(svgRef.current);
    svg.selectAll("*").remove();

    const innerW = WIDTH - MARGIN.left - MARGIN.right;
    const innerH = HEIGHT - MARGIN.top - MARGIN.bottom;

    const g = svg
      .attr("width", WIDTH)
      .attr("height", HEIGHT)
      .append("g")
      .attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);

    // X scale
    const xMax = Math.max(imageScale * 4, idealRangeHigh) * 1.2;
    const xScale = scaleLinear().domain([0, xMax]).range([0, innerW]);

    // Y scale (band)
    const yScale = scaleBand()
      .domain(BINNING_LABELS)
      .range([0, innerH])
      .padding(0.2);

    // Ideal zone shaded rectangle
    g.append("rect")
      .attr("x", xScale(idealRangeLow))
      .attr("y", 0)
      .attr("width", xScale(idealRangeHigh) - xScale(idealRangeLow))
      .attr("height", innerH)
      .attr("fill", IDEAL_ZONE_FILL);

    // Ideal zone label
    const zoneMidX =
      (xScale(idealRangeLow) + xScale(idealRangeHigh)) / 2;
    g.append("text")
      .attr("x", zoneMidX)
      .attr("y", -7)
      .attr("text-anchor", "middle")
      .attr("fill", "#1565c0")
      .attr("font-size", "11px")
      .attr("font-weight", 600)
      .text("Ideal Range");

    // Ideal zone dashed borders
    [idealRangeLow, idealRangeHigh].forEach((val) => {
      g.append("line")
        .attr("x1", xScale(val))
        .attr("x2", xScale(val))
        .attr("y1", 0)
        .attr("y2", innerH)
        .attr("stroke", "#64b5f6")
        .attr("stroke-width", 1)
        .attr("stroke-dasharray", "4,3");
    });

    // Bars
    const bandHeight = yScale.bandwidth();
    const barHeight = bandHeight * 0.6;
    const barOffset = (bandHeight - barHeight) / 2;

    BINNING_LEVELS.forEach((bin, i) => {
      const label = BINNING_LABELS[i];
      const scaledValue = imageScale * bin;
      const assessment = binningRecommendations[bin];
      const color =
        assessment === "well_sampled"
          ? BLUE
          : assessment === "oversampled"
            ? ORANGE
            : TEAL;
      const yPos = (yScale(label) ?? 0) + barOffset;

      // Bar
      g.append("rect")
        .attr("x", 0)
        .attr("y", yPos)
        .attr("width", xScale(scaledValue))
        .attr("height", barHeight)
        .attr("fill", color)
        .attr("rx", 2);

      // Value label on bar
      const barW = xScale(scaledValue);
      const labelText = scaledValue.toFixed(2);
      const labelInside = barW > 40;

      g.append("text")
        .attr("x", labelInside ? barW - 4 : barW + 4)
        .attr("y", yPos + barHeight / 2)
        .attr("dy", "0.35em")
        .attr("text-anchor", labelInside ? "end" : "start")
        .attr("fill", labelInside ? "#ffffff" : TEXT_COLOR)
        .attr("font-size", "12px")
        .attr("font-weight", 500)
        .text(labelText);
    });

    // X axis
    const xAxis = axisBottom(xScale)
      .ticks(5)
      .tickFormat((d) => `${d}\u2033/px`);

    const xAxisG = g
      .append("g")
      .attr("transform", `translate(0,${innerH})`)
      .call(xAxis);

    // Force fill and font on D3-generated tick labels
    xAxisG.selectAll(".tick text")
      .attr("fill", TEXT_COLOR)
      .attr("font-size", "12px")
      .style("fill", TEXT_COLOR);

    // X axis title
    g.append("text")
      .attr("x", innerW / 2)
      .attr("y", innerH + 38)
      .attr("text-anchor", "middle")
      .attr("fill", TEXT_COLOR)
      .attr("font-size", "12px")
      .text("Image Scale (\u2033/pixel)");

    // Y axis labels (manual — no axis line)
    BINNING_LABELS.forEach((label) => {
      g.append("text")
        .attr("x", -8)
        .attr("y", (yScale(label) ?? 0) + bandHeight / 2)
        .attr("dy", "0.35em")
        .attr("text-anchor", "end")
        .attr("fill", TEXT_COLOR)
        .attr("font-size", "12px")
        .text(label);
    });

    // Y axis title
    g.append("text")
      .attr("transform", `translate(${-MARGIN.left + 12},${innerH / 2}) rotate(-90)`)
      .attr("text-anchor", "middle")
      .attr("fill", TEXT_COLOR)
      .attr("font-size", "12px")
      .text("Binning");
  }, [imageScale, idealRangeLow, idealRangeHigh, binningRecommendations]);

  return <svg ref={svgRef} />;
}
