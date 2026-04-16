import { useEffect, useRef } from "react";
import { scaleLinear, scaleBand, select, axisBottom } from "d3";

interface SamplingChartProps {
  imageScale: number; // unbinned arcsec/pixel
  idealRangeLow: number; // arcsec/pixel
  idealRangeHigh: number; // arcsec/pixel
  binningRecommendations: Record<number, string>; // {1: "oversampled", 2: "well_sampled", ...}
}

const WIDTH = 350;
const HEIGHT = 185;
const MARGIN = { top: 20, right: 20, bottom: 45, left: 50 };

const BLUE = "#1976d2";    // well sampled
const ORANGE = "#ed6c02";  // oversampled (too fine, wasting SNR)
const TEAL = "#00695c";    // undersampled (too coarse, blocky stars)
const IDEAL_ZONE_FILL = "#e3f2fd";

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
      .attr("y", -6)
      .attr("text-anchor", "middle")
      .attr("fill", "#90caf9")
      .attr("font-size", "10px")
      .attr("font-weight", 600)
      .text("Ideal Range");

    // Ideal zone dashed borders
    [idealRangeLow, idealRangeHigh].forEach((val) => {
      g.append("line")
        .attr("x1", xScale(val))
        .attr("x2", xScale(val))
        .attr("y1", 0)
        .attr("y2", innerH)
        .attr("stroke", "#90caf9")
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
        .attr("fill", labelInside ? "#ffffff" : "#666666")
        .attr("font-size", "11px")
        .text(labelText);
    });

    // X axis
    const xAxis = axisBottom(xScale)
      .ticks(5)
      .tickFormat((d) => `${d}\u2033/px`);

    g.append("g")
      .attr("transform", `translate(0,${innerH})`)
      .call(xAxis)
      .selectAll("text")
      .attr("font-size", "11px")
      .attr("fill", "#333333");

    // X axis title
    g.append("text")
      .attr("x", innerW / 2)
      .attr("y", innerH + 35)
      .attr("text-anchor", "middle")
      .attr("fill", "#333333")
      .attr("font-size", "11px")
      .text("Image Scale (\u2033/pixel)");

    // Y axis labels (manual — no axis line)
    BINNING_LABELS.forEach((label) => {
      g.append("text")
        .attr("x", -8)
        .attr("y", (yScale(label) ?? 0) + bandHeight / 2)
        .attr("dy", "0.35em")
        .attr("text-anchor", "end")
        .attr("fill", "#333333")
        .attr("font-size", "11px")
        .text(label);
    });

    // Y axis title
    g.append("text")
      .attr("transform", `translate(${-MARGIN.left + 10},${innerH / 2}) rotate(-90)`)
      .attr("text-anchor", "middle")
      .attr("fill", "#333333")
      .attr("font-size", "11px")
      .text("Binning");
  }, [imageScale, idealRangeLow, idealRangeHigh, binningRecommendations]);

  return <svg ref={svgRef} />;
}
