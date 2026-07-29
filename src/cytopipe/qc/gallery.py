"""Self-contained HTML gallery for manually reviewing per-image QC metrics."""

import base64
import json
from pathlib import Path

import pandas as pd

from cytopipe.columns import METADATA_PLATE, METADATA_SITE, METADATA_WELL

from .scan import channel_columns


def _json_default(value):
    """Fallback for json.dumps: unwrap numpy scalars (e.g. int64/float64) to native Python."""
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _thumbnail_data_uri(path: Path | None) -> str:
    if path is None:
        return ""
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_gallery(metrics: pd.DataFrame, out_html: Path) -> Path:
    """Write a self-contained HTML review gallery to ``out_html`` and return the path.

    Embeds one thumbnail plus per-channel ``PowerLogLogSlope`` values per image as a JSON blob,
    together with a min/max number-input pair per channel (starting empty/unbounded). Each
    channel is plotted as a column of dots (one per image); thresholds are set by editing the
    inputs, out-of-range dots recolor live, and a button downloads the current exclusion list as
    a CSV, no server round trip involved. Thumbnails travel with the data (never a filesystem
    path) since review commonly happens on a different machine than the one that generated the
    images (e.g. downloaded off an HPC), so a dot's image is decoded into the DOM only when that
    dot (or its table row) is clicked, not eagerly for every image up front.
    """
    columns = channel_columns(metrics)
    channels = sorted(columns)

    rows = [
        {
            "plate": row[METADATA_PLATE],
            "well": row[METADATA_WELL],
            "site": row[METADATA_SITE],
            "thumb": _thumbnail_data_uri(row["overlay_path"]),
            "values": {channel: row[columns[channel]] for channel in channels},
        }
        for _, row in metrics.iterrows()
    ]

    html = (
        _HTML_TEMPLATE.replace("__CHANNELS_JSON__", json.dumps(channels))
        .replace("__ROWS_JSON__", json.dumps(rows, default=_json_default))
    )

    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html)
    return out_html


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>QC image review</title>
<style>
  :root {
    color-scheme: light;
    --surface-1:      #fcfcfb;
    --page:           #f9f9f7;
    --text-primary:   #0b0b0b;
    --text-secondary: #52514e;
    --muted:          #898781;
    --gridline:       #e1e0d9;
    --baseline:       #c3c2b7;
    --good:           #0ca30c;
    --critical:       #d03b3b;
    --border:         rgba(11, 11, 11, 0.10);
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) {
      color-scheme: dark;
      --surface-1:      #1a1a19;
      --page:           #0d0d0d;
      --text-primary:   #ffffff;
      --text-secondary: #c3c2b7;
      --muted:          #898781;
      --gridline:       #2c2c2a;
      --baseline:       #383835;
      --good:           #0ca30c;
      --critical:       #e66767;
      --border:         rgba(255, 255, 255, 0.10);
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --surface-1:      #1a1a19;
    --page:           #0d0d0d;
    --text-primary:   #ffffff;
    --text-secondary: #c3c2b7;
    --muted:          #898781;
    --gridline:       #2c2c2a;
    --baseline:       #383835;
    --good:           #0ca30c;
    --critical:       #e66767;
    --border:         rgba(255, 255, 255, 0.10);
  }

  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 1.5rem; background: var(--page); color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height: 1.4;
  }
  h1 { font-size: 1.25rem; margin: 0 0 0.25rem; }
  p.hint { color: var(--text-secondary); max-width: 60em; margin-top: 0.25rem; }
  code { color: var(--text-primary); }

  #controls {
    display: flex; flex-wrap: wrap; gap: 1rem; align-items: end;
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px;
    padding: 0.75rem 1rem; margin: 1rem 0;
  }
  .channel-range {
    display: flex; flex-direction: column; gap: 0.25rem;
    font-size: 0.85rem; color: var(--text-secondary);
  }
  .channel-range strong { color: var(--text-primary); }
  .channel-range .inputs { display: flex; gap: 0.35rem; align-items: center; }
  .channel-range input {
    width: 5.5rem; background: var(--page); color: var(--text-primary);
    border: 1px solid var(--border); border-radius: 4px; padding: 0.25rem 0.4rem; font: inherit;
  }

  #summary-row {
    display: flex; flex-wrap: wrap; align-items: center; gap: 1.25rem; margin: 0 0 1rem;
  }
  #summary { font-weight: 600; }
  .legend {
    display: flex; gap: 1.25rem; align-items: center;
    font-size: 0.85rem; color: var(--text-secondary);
  }
  .legend .swatch {
    width: 10px; height: 10px; border-radius: 50%;
    display: inline-block; margin-right: 0.4rem;
  }
  .legend .swatch.good { background: var(--good); }
  .legend .swatch.critical { background: var(--critical); }
  #download {
    margin-left: auto; padding: 0.5rem 1rem; border-radius: 6px; border: 1px solid var(--border);
    background: var(--surface-1); color: var(--text-primary); cursor: pointer;
    font-weight: 600; font: inherit;
  }
  #download:hover { background: var(--page); }

  #main { display: flex; gap: 1.25rem; align-items: flex-start; flex-wrap: wrap; }
  #chart-card {
    flex: 1 1 640px; min-width: 320px;
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 8px; padding: 1rem;
  }
  #chart-wrap { position: relative; width: 100%; }
  canvas#chart { width: 100%; height: 420px; display: block; cursor: crosshair; }

  #tooltip {
    position: absolute; pointer-events: none;
    background: var(--text-primary); color: var(--surface-1);
    font-size: 0.75rem; padding: 0.3rem 0.5rem; border-radius: 4px;
    transform: translate(-50%, -125%);
    white-space: nowrap; opacity: 0; transition: opacity 0.1s;
  }
  #tooltip .value { font-weight: 700; margin-right: 0.35rem; }
  #tooltip .meta { opacity: 0.85; }

  #preview-card {
    flex: 0 0 260px;
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 8px; padding: 1rem;
    position: sticky; top: 1rem;
  }
  #preview-card h2 {
    font-size: 0.9rem; margin: 0 0 0.75rem; color: var(--text-secondary); font-weight: 600;
  }
  #preview-image-wrap {
    width: 100%; aspect-ratio: 1; background: var(--page); border-radius: 6px; overflow: hidden;
    display: flex; align-items: center; justify-content: center;
    color: var(--muted); font-size: 0.8rem; text-align: center;
  }
  #preview-image-wrap img { width: 100%; height: 100%; object-fit: cover; }
  #preview-meta { margin: 0.75rem 0 0; font-size: 0.85rem; }
  #preview-meta dt { color: var(--text-secondary); }
  #preview-meta dd { margin: 0 0 0.4rem; font-weight: 600; font-variant-numeric: tabular-nums; }

  details#table-view { margin-top: 1.5rem; }
  details#table-view > summary {
    cursor: pointer; font-weight: 600; padding: 0.5rem 0; color: var(--text-secondary);
  }
  table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
  th, td { padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--gridline); text-align: left; }
  th {
    position: sticky; top: 0; background: var(--surface-1); cursor: pointer; user-select: none;
    color: var(--text-secondary); font-weight: 600;
  }
  th.sorted::after { content: " ▾"; }
  tr.flagged-row td:first-child { box-shadow: inset 3px 0 var(--critical); }
  tr.row-selected { background: color-mix(in srgb, var(--text-primary) 6%, transparent); }
  td.out-of-range { color: var(--critical); font-weight: 600; }
  .row-btn {
    border: 1px solid var(--border); background: var(--page); color: var(--text-primary);
    font: inherit; border-radius: 4px; padding: 0.15rem 0.5rem; cursor: pointer; font-size: 0.8rem;
  }
</style>
</head>
<body>
<h1>QC image review</h1>
<p class="hint">
  Each column is a channel; each dot is one image's blur score on that channel (its position
  within the column is just jitter to keep dots apart, it carries no meaning). Set a min/max per
  channel below to flag images by eye — an image's dots turn red on every channel, not only the
  one that tripped a threshold, since a flagged image gets excluded outright, not one channel of
  it. Click a dot, or a row in the table below, to load that image on the right: images travel
  with this file but are only decoded when you ask for one, not all up front. When satisfied,
  click &quot;Download exclusion list&quot; to save a CSV of the flagged Plate/Well/Site rows,
  then point <code>--qc_exclude_file</code> at that file.
</p>

<div id="controls"></div>

<div id="summary-row">
  <span id="summary"></span>
  <span class="legend">
    <span><span class="swatch good"></span>Normal</span>
    <span><span class="swatch critical"></span>Flagged</span>
  </span>
  <button id="download" type="button">Download exclusion list</button>
</div>

<div id="main">
  <div id="chart-card">
    <div id="chart-wrap">
      <canvas id="chart"></canvas>
      <div id="tooltip"><span class="value"></span><span class="meta"></span></div>
    </div>
  </div>
  <div id="preview-card">
    <h2>Selected image</h2>
    <div id="preview-image-wrap"><span>Click a point to load its image</span></div>
    <dl id="preview-meta"></dl>
  </div>
</div>

<details id="table-view">
  <summary>Table view (<span id="table-count"></span> images)</summary>
  <div style="overflow-x:auto">
    <table>
      <thead><tr id="header-row"></tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </div>
</details>

<script>
const CHANNELS = __CHANNELS_JSON__;
const ROWS = __ROWS_JSON__;

const controlsEl = document.getElementById("controls");
const summaryEl = document.getElementById("summary");
const canvas = document.getElementById("chart");
const ctx = canvas.getContext("2d");
const chartWrap = document.getElementById("chart-wrap");
const tooltipEl = document.getElementById("tooltip");
const tooltipValueEl = tooltipEl.querySelector(".value");
const tooltipMetaEl = tooltipEl.querySelector(".meta");
const previewImageWrap = document.getElementById("preview-image-wrap");
const previewMetaEl = document.getElementById("preview-meta");
const headerRowEl = document.getElementById("header-row");
const rowsEl = document.getElementById("rows");
const tableCountEl = document.getElementById("table-count");

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function rowKey(row) {
  return row.plate + "|" + row.well + "|" + row.site;
}

// Deterministic per-point horizontal jitter in [-1, 1] so re-render/resize never reshuffles dots.
function hashJitter(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const unit = ((h >>> 0) % 100000) / 100000;
  return unit * 2 - 1;
}

function currentBound(channel, side) {
  const el = document.getElementById(`range-${channel}-${side}`);
  const value = el.value.trim();
  return value === "" ? null : Number(value);
}

function channelOutOfRange(channel, value) {
  const low = currentBound(channel, "min");
  const high = currentBound(channel, "max");
  return (low !== null && value < low) || (high !== null && value > high);
}

function rowExcluded(row) {
  return CHANNELS.some((channel) => channelOutOfRange(channel, row.values[channel]));
}

// One point per (row, channel): what the chart plots.
const POINTS = [];
for (const row of ROWS) {
  for (const channel of CHANNELS) {
    POINTS.push({
      row,
      channel,
      value: row.values[channel],
      jitter: hashJitter(`${rowKey(row)}|${channel}`),
    });
  }
}

function valueDomain() {
  let min = Infinity;
  let max = -Infinity;
  for (const p of POINTS) {
    if (p.value < min) min = p.value;
    if (p.value > max) max = p.value;
  }
  if (!Number.isFinite(min)) {
    min = 0;
    max = 1;
  }
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * 0.08;
  return [min - pad, max + pad];
}

const [Y_MIN, Y_MAX] = valueDomain();

let selectedKey = null;
let plotBounds = null;

function buildControls() {
  for (const channel of CHANNELS) {
    const wrap = document.createElement("div");
    wrap.className = "channel-range";
    const label = document.createElement("strong");
    label.textContent = channel;
    const inputs = document.createElement("div");
    inputs.className = "inputs";
    const minInput = document.createElement("input");
    minInput.type = "number";
    minInput.step = "any";
    minInput.placeholder = "min";
    minInput.id = `range-${channel}-min`;
    const maxInput = document.createElement("input");
    maxInput.type = "number";
    maxInput.step = "any";
    maxInput.placeholder = "max";
    maxInput.id = `range-${channel}-max`;
    minInput.addEventListener("input", renderAll);
    maxInput.addEventListener("input", renderAll);
    inputs.append(minInput, document.createTextNode(" - "), maxInput);
    wrap.append(label, inputs);
    controlsEl.append(wrap);
  }
}

const TABLE_COLUMNS = ["plate", "well", "site", ...CHANNELS];
const LABELS = { plate: "Plate", well: "Well", site: "Site" };
let sortKey = null;
let sortAsc = true;

function buildTableHeader() {
  for (const column of TABLE_COLUMNS) {
    const th = document.createElement("th");
    th.textContent = LABELS[column] || column;
    th.dataset.column = column;
    th.addEventListener("click", () => {
      sortAsc = sortKey === column ? !sortAsc : true;
      sortKey = column;
      renderTable();
    });
    headerRowEl.append(th);
  }
  const imageTh = document.createElement("th");
  imageTh.textContent = "Image";
  headerRowEl.append(imageTh);
}

function sortedRows() {
  if (!sortKey) return ROWS;
  const value = (row) => (sortKey in row.values ? row.values[sortKey] : row[sortKey]);
  return [...ROWS].sort((a, b) => {
    const av = value(a);
    const bv = value(b);
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortAsc ? cmp : -cmp;
  });
}

function renderTable() {
  for (const th of headerRowEl.children) {
    th.classList.toggle("sorted", th.dataset.column === sortKey);
  }
  rowsEl.textContent = "";
  for (const row of sortedRows()) {
    const tr = document.createElement("tr");
    const classes = [];
    if (rowExcluded(row)) classes.push("flagged-row");
    if (rowKey(row) === selectedKey) classes.push("row-selected");
    tr.className = classes.join(" ");
    for (const column of TABLE_COLUMNS) {
      const td = document.createElement("td");
      if (column in row.values) {
        const value = row.values[column];
        td.textContent = value;
        if (channelOutOfRange(column, value)) td.classList.add("out-of-range");
      } else {
        td.textContent = row[column];
      }
      tr.append(td);
    }
    const imageTd = document.createElement("td");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "row-btn";
    btn.textContent = "View";
    btn.addEventListener("click", () => selectRow(row));
    imageTd.append(btn);
    tr.append(imageTd);
    rowsEl.append(tr);
  }
}

function selectRow(row) {
  selectedKey = rowKey(row);

  previewImageWrap.textContent = "";
  if (row.thumb) {
    const img = document.createElement("img");
    img.src = row.thumb;
    img.alt = `${row.plate} ${row.well} site ${row.site}`;
    previewImageWrap.append(img);
  } else {
    const span = document.createElement("span");
    span.textContent = "No overlay image for this row";
    previewImageWrap.append(span);
  }

  previewMetaEl.textContent = "";
  const entries = [
    ["Plate", row.plate],
    ["Well", row.well],
    ["Site", row.site],
    ...CHANNELS.map((channel) => [channel, row.values[channel].toFixed(3)]),
  ];
  for (const [label, value] of entries) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    previewMetaEl.append(dt, dd);
  }

  redrawChart();
  renderTable();
}

function resizeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  const rect = chartWrap.getBoundingClientRect();
  const cssHeight = canvas.clientHeight || 420;
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  drawChart(rect.width, cssHeight);
}

function redrawChart() {
  if (plotBounds) drawChart(plotBounds.width, plotBounds.height);
}

function drawChart(width, height) {
  const good = cssVar("--good");
  const critical = cssVar("--critical");
  const surface = cssVar("--surface-1");
  const gridline = cssVar("--gridline");
  const muted = cssVar("--muted");
  const textPrimary = cssVar("--text-primary");

  const marginLeft = 46;
  const marginRight = 12;
  const marginTop = 12;
  const marginBottom = 28;
  const plotW = Math.max(1, width - marginLeft - marginRight);
  const plotH = Math.max(1, height - marginTop - marginBottom);
  const bandW = plotW / CHANNELS.length;

  const yScale = (value) => marginTop + plotH * (1 - (value - Y_MIN) / (Y_MAX - Y_MIN));
  const xCenter = (channelIndex) => marginLeft + bandW * (channelIndex + 0.5);

  ctx.clearRect(0, 0, width, height);

  ctx.strokeStyle = gridline;
  ctx.lineWidth = 1;
  ctx.fillStyle = muted;
  ctx.font = "11px system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  const tickCount = 5;
  for (let i = 0; i <= tickCount; i++) {
    const value = Y_MIN + ((Y_MAX - Y_MIN) * i) / tickCount;
    const y = Math.round(yScale(value)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(marginLeft, y);
    ctx.lineTo(marginLeft + plotW, y);
    ctx.stroke();
    ctx.fillText(value.toFixed(1), marginLeft - 8, y);
  }

  ctx.strokeStyle = cssVar("--baseline");
  ctx.beginPath();
  const baselineY = Math.round(marginTop + plotH) + 0.5;
  ctx.moveTo(marginLeft, baselineY);
  ctx.lineTo(marginLeft + plotW, baselineY);
  ctx.stroke();

  ctx.fillStyle = textPrimary;
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.font = "12px system-ui, sans-serif";
  CHANNELS.forEach((channel, i) => {
    ctx.fillText(channel, xCenter(i), marginTop + plotH + 8);
  });

  const channelIndex = Object.fromEntries(CHANNELS.map((c, i) => [c, i]));
  // A row's every dot (across all channels) shares one flagged/normal color, since the image
  // itself is what gets excluded, not one channel's reading of it in isolation.
  const excludedKeys = new Set(ROWS.filter(rowExcluded).map(rowKey));
  const radius = 4;
  for (const p of POINTS) {
    const cx = xCenter(channelIndex[p.channel]) + p.jitter * (bandW * 0.32);
    const cy = yScale(p.value);
    const flagged = excludedKeys.has(rowKey(p.row));

    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = flagged ? critical : good;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = surface;
    ctx.stroke();

    if (rowKey(p.row) === selectedKey) {
      ctx.beginPath();
      ctx.arc(cx, cy, radius + 3, 0, Math.PI * 2);
      ctx.lineWidth = 2;
      ctx.strokeStyle = textPrimary;
      ctx.stroke();
    }
  }

  plotBounds = { marginLeft, marginTop, plotW, plotH, bandW, yScale, channelIndex, width, height };
}

// Dense scatter: only search the channel column under the pointer, then nearest-point within it,
// rather than requiring the pointer to land dead-center on an ~8px dot.
function nearestPoint(mx, my) {
  if (!plotBounds) return null;
  const { marginLeft, bandW } = plotBounds;
  const bandIndex = Math.min(
    CHANNELS.length - 1,
    Math.max(0, Math.floor((mx - marginLeft) / bandW)),
  );
  const channel = CHANNELS[bandIndex];
  const xCenter = marginLeft + bandW * (bandIndex + 0.5);

  let best = null;
  let bestDist = Infinity;
  for (const p of POINTS) {
    if (p.channel !== channel) continue;
    const cx = xCenter + p.jitter * (bandW * 0.32);
    const cy = plotBounds.yScale(p.value);
    const dx = mx - cx;
    const dy = my - cy;
    const dist = dx * dx + dy * dy;
    if (dist < bestDist) {
      bestDist = dist;
      best = p;
    }
  }
  const maxDist = 16 * 16;
  return bestDist <= maxDist ? best : null;
}

function eventPoint(evt) {
  const rect = canvas.getBoundingClientRect();
  return [evt.clientX - rect.left, evt.clientY - rect.top];
}

canvas.addEventListener("pointermove", (evt) => {
  const [mx, my] = eventPoint(evt);
  const hit = nearestPoint(mx, my);
  if (hit) {
    tooltipEl.style.opacity = "1";
    tooltipEl.style.left = `${mx}px`;
    tooltipEl.style.top = `${my}px`;
    tooltipValueEl.textContent = hit.value.toFixed(3);
    tooltipMetaEl.textContent =
      `${hit.channel} · ${hit.row.plate} ${hit.row.well} site ${hit.row.site}`;
    canvas.style.cursor = "pointer";
  } else {
    tooltipEl.style.opacity = "0";
    canvas.style.cursor = "crosshair";
  }
});

canvas.addEventListener("pointerleave", () => {
  tooltipEl.style.opacity = "0";
});

canvas.addEventListener("click", (evt) => {
  const [mx, my] = eventPoint(evt);
  const hit = nearestPoint(mx, my);
  if (hit) selectRow(hit.row);
});

function renderAll() {
  const flaggedCount = ROWS.filter(rowExcluded).length;
  summaryEl.textContent = `${flaggedCount} of ${ROWS.length} images currently flagged`;
  redrawChart();
  renderTable();
}

function csvEscape(value) {
  const text = String(value);
  return /[",\\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadExclusions() {
  const excluded = ROWS.filter(rowExcluded);
  const lines = ["Metadata_Plate,Metadata_Well,Metadata_Site"];
  for (const row of excluded) {
    lines.push([row.plate, row.well, row.site].map(csvEscape).join(","));
  }
  const blob = new Blob([lines.join("\\n") + "\\n"], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "excluded.csv";
  a.click();
  URL.revokeObjectURL(url);
}

document.getElementById("download").addEventListener("click", downloadExclusions);
window.addEventListener("resize", resizeCanvas);
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", redrawChart);
new MutationObserver(redrawChart).observe(document.documentElement, {
  attributes: true,
  attributeFilter: ["data-theme"],
});

buildControls();
buildTableHeader();
tableCountEl.textContent = ROWS.length;
resizeCanvas();
renderAll();
</script>
</body>
</html>
"""
