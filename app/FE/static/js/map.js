const thresholds = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60];
const colors = [
  "#eaf4f2", "#d2e8e4", "#b6d9d2", "#98c8bf", "#79b7ab",
  "#5ba697", "#3f9583", "#2a8270", "#1a6f5e", "#0d5c4d",
  "#034a3d", "#023629", "#01241b"
];
const noDataPatternId = "nodata";

function colorFor(v) {
  if (v == null || isNaN(v)) return `url(#${noDataPatternId})`;
  for (let i = 0; i < thresholds.length; i++) {
    if (v < thresholds[i]) return colors[i];
  }
  return colors[colors.length - 1];
}

const svg = d3.select("#map");
const width = 960, height = 500;

const defs = svg.append("defs");
const pat = defs.append("pattern")
  .attr("id", noDataPatternId)
  .attr("patternUnits", "userSpaceOnUse")
  .attr("width", 6).attr("height", 6)
  .attr("patternTransform", "rotate(45)");
pat.append("rect").attr("width", 6).attr("height", 6).attr("fill", "#ffffff");
pat.append("line").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 6)
  .attr("stroke", "#d9d9d9").attr("stroke-width", 3);

const projection = d3.geoEqualEarth()
  .scale(175)
  .translate([width / 2, height / 2 + 10]);
const path = d3.geoPath(projection);
const tooltip = d3.select("#tooltip");

Promise.all([
  fetch("/api/tax-data").then(r => r.json()),
  d3.json("https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json")
]).then(([data, world]) => {
  const countries = topojson.feature(world, world.objects.countries).features;

  svg.append("g")
    .selectAll("path")
    .data(countries)
    .join("path")
      .attr("class", "country")
      .attr("d", path)
      .attr("fill", d => colorFor(data[d.properties.name]))
      .on("mousemove", function(event, d) {
        const name = d.properties.name;
        const v = data[name];
        tooltip
          .style("left", (event.offsetX + 14) + "px")
          .style("top",  (event.offsetY + 14) + "px")
          .style("opacity", 1)
          .html(
            `<div class="t-name">${name}</div>` +
            (v == null
              ? `<div class="t-nodata">No data</div>`
              : `<div class="t-val">${v.toFixed(1)}%</div>`)
          );
      })
      .on("mouseleave", function() {
        tooltip.style("opacity", 0);
      });

}).catch(err => {
  document.getElementById("map-container").innerHTML =
    `<div style="padding:20px;color:#b00;">Could not load map data: ${err}</div>`;
});

/* Legend */
const legend = document.getElementById("legend");
legend.innerHTML = `
  <span class="legend-endlabel">0</span>
  <div class="legend-cells" id="legend-cells"></div>
  <span class="legend-endlabel">&gt; 60</span>
  <span class="legend-unit">% of GDP</span>
`;
const cellsWrap = document.getElementById("legend-cells");
colors.forEach(c => {
  const cell = document.createElement("div");
  cell.className = "legend-cell";
  cell.style.width = "22px";
  cell.style.background = c;
  cellsWrap.appendChild(cell);
});
