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


def _row_key(plate, well, site) -> str:
    return f"{plate}|{well}|{site}"


def build_gallery(metrics: pd.DataFrame, out_html: Path) -> Path:
    """Write a self-contained HTML review gallery to ``out_html`` and return the path.

    Embeds per-channel ``PowerLogLogSlope`` values per image as a JSON blob, together with a
    min/max number-input pair per channel (starting empty/unbounded).
    """
    columns = channel_columns(metrics)
    channels = sorted(columns)

    rows = []
    thumb_tags = []
    for _, row in metrics.iterrows():
        plate, well, site = row[METADATA_PLATE], row[METADATA_WELL], row[METADATA_SITE]
        overlay_path = row["overlay_path"]
        rows.append(
            {
                "plate": plate,
                "well": well,
                "site": site,
                "hasThumb": overlay_path is not None,
                "values": {channel: row[columns[channel]] for channel in channels},
            }
        )
        if overlay_path is not None:
            key = _row_key(plate, well, site)
            thumb_tags.append(f'<img data-key="{key}" src="{_thumbnail_data_uri(overlay_path)}">')

    document = (
        _HTML_TEMPLATE.replace("__CHANNELS_JSON__", json.dumps(channels))
        .replace("__ROWS_JSON__", json.dumps(rows, default=_json_default))
        .replace("__THUMBS_HTML__", "".join(thumb_tags))
    )

    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(document)
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
  canvas#chart { width: 100%; height: 640px; display: block; cursor: crosshair; }

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
  Each column is a channel. The thin outline traces that channel's blur-score distribution
  across every image. There are too many images to plot every one as its own dot, so green
  dots are a fixed representative sample of normal images and red dots are every image
  currently flagged. Set a min/max per channel below to flag images by eye. An image's dots
  turn red on every channel, not only the one that tripped a threshold, since a flagged image
  gets excluded outright, not one channel of it. Click a dot, or a row in the table below, to
  load that image on the right. When satisfied, click &quot;Download exclusion list&quot; to
  save a CSV of the flagged Plate/Well/Site rows, then point <code>--qc_exclude_file</code> at
  that file.
</p>

<div id="controls"></div>

<div id="summary-row">
  <span id="summary"></span>
  <span class="legend">
    <span><span class="swatch good"></span>Normal (sampled)</span>
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

<!--
  Thumbnails live here, outside the ROWS array below: the HTML parser streams plain markup
  cheaply, whereas the JS engine would have to fully materialize every thumbnail as a live
  string object before the page could do anything if they sat in ROWS instead, which is what
  used to make real (multi-plate, tens-of-thousands-of-image) runs unusable. Looked up by
  plate|well|site key and cloned into the preview pane only when a dot/row is clicked.
-->
<div id="thumb-store" hidden>__THUMBS_HTML__</div>

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

// Chart geometry shared between the one-time swarm/density layout below and drawChart's
// per-frame rendering, so both agree on where things sit. Canvas height is fixed via CSS
// (640px) while width responds to the window, so layout is done once against this fixed
// height and expressed horizontally as a fraction of the (resize-dependent) band width —
// applied fresh at draw time, same trick the old random-jitter version used.
const MARGIN_LEFT = 46;
const MARGIN_RIGHT = 12;
const MARGIN_TOP = 12;
const MARGIN_BOTTOM = 28;
const CHART_HEIGHT = 640;
const DOT_RADIUS = 4;
const DOT_SPACING = DOT_RADIUS * 2 + 1; // 1px gap between touching dots
const SWARM_MAX_FRACTION = 0.42; // of a channel's band width, each side

function currentBound(channel, side) {
  const el = document.getElementById(`range-${channel}-${side}`);
  const value = el.value.trim();
  return value === "" ? null : Number(value);
}

// Reads every min/max input once per render pass. channelOutOfRange/rowExcluded run per
// row (or per row per channel) over up to tens of thousands of rows, so a fresh
// getElementById per check here would multiply into hundreds of thousands of DOM lookups.
function computeBounds() {
  const bounds = {};
  for (const channel of CHANNELS) {
    bounds[channel] = [currentBound(channel, "min"), currentBound(channel, "max")];
  }
  return bounds;
}

function channelOutOfRange(bounds, channel, value) {
  const [low, high] = bounds[channel];
  return (low !== null && value < low) || (high !== null && value > high);
}

function rowExcluded(bounds, row) {
  return CHANNELS.some((channel) => channelOutOfRange(bounds, channel, row.values[channel]));
}

// Recomputed once whenever a range input changes, then reused as-is by chart/table redraws
// that only a selection click (not a filter change) triggers.
let currentBounds = null;
let currentExcludedKeys = null;
let currentDisplayedPoints = []; // every currently-flagged point, plus the stable normal sample
let displayedPointsByChannel = new Map();

function refreshDerived() {
  currentBounds = computeBounds();
  currentExcludedKeys = new Set(
    ROWS.filter((row) => rowExcluded(currentBounds, row)).map(rowKey),
  );
  // A sampled point that's now flagged shows up via the first branch (red), not the second
  // (green) — it doesn't get drawn twice, it just changes color like any other flagged point.
  currentDisplayedPoints = POINTS.filter(
    (p) => currentExcludedKeys.has(p.key) || NORMAL_SAMPLE.has(p),
  );
  displayedPointsByChannel = layoutSwarm(currentDisplayedPoints);
}

// Thumbnails, keyed by plate|well|site; populated from the hidden markup, never from ROWS.
const THUMBS = new Map();
for (const img of document.querySelectorAll("#thumb-store img")) {
  THUMBS.set(img.dataset.key, img);
}

// One point per (row, channel): what the chart plots. Also indexed by channel so hovering
// only has to scan the ~one-fifth of points in the column under the pointer.
const POINTS = [];
const POINTS_BY_CHANNEL = new Map(CHANNELS.map((channel) => [channel, []]));
for (const row of ROWS) {
  for (const channel of CHANNELS) {
    const point = { row, channel, key: rowKey(row), value: row.values[channel] };
    POINTS.push(point);
    POINTS_BY_CHANNEL.get(channel).push(point);
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

// Swarm layout: each point stays at its true value (y never moves) and is nudged only
// horizontally to the nearest free spot, exactly like a standard beeswarm/sina plot — as
// opposed to snapping onto a rigid row/column grid, which reads as artificial banding rather
// than an organic cluster. Only run on demand (see layoutSwarm below) over whichever points
// are currently flagged — a real run's full ~25k points per channel simply can't fit as
// individual dots in a compact chart, so the chart shows the always-on density outline for
// "everything" and dots only for the (usually far smaller, and far more relevant to actually
// review) currently-excluded set.
const REFERENCE_PLOT_WIDTH = 640 - MARGIN_LEFT - MARGIN_RIGHT;
const REFERENCE_BAND_W = REFERENCE_PLOT_WIDTH / CHANNELS.length;
const MAX_HALF_WIDTH_PX = REFERENCE_BAND_W * SWARM_MAX_FRACTION;
const SWARM_STEP = DOT_SPACING;
const MAX_STEPS = Math.max(1, Math.floor(MAX_HALF_WIDTH_PX / SWARM_STEP));
const LANES = MAX_STEPS * 2 + 1; // distinct non-overlapping x positions the column can hold
const LAYOUT_PLOT_HEIGHT = CHART_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM;
// In a pathologically dense cluster, checking every already-placed nearby point before
// giving up and accepting overlap would be unbounded; capping the search keeps each point's
// placement cost bounded regardless of how many points share nearly the same value.
const MAX_COLLISION_CHECKS = 60;

function layoutYScale(value) {
  return MARGIN_TOP + LAYOUT_PLOT_HEIGHT * (1 - (value - Y_MIN) / (Y_MAX - Y_MIN));
}

// Places one channel's points left-to-right in ascending value order (so the swarm grows as
// a coherent shape, not in an arbitrary order), searching outward from center for the
// nearest x that doesn't collide with any already-placed point within DOT_SPACING.
function layoutChannelSwarm(points) {
  const sorted = [...points].sort((a, b) => a.value - b.value);
  const placed = []; // {x, y}, appended in the same (monotonic-in-y) order as sorted
  let windowStart = 0;

  for (const p of sorted) {
    const y = layoutYScale(p.value);
    // Points placed long enough ago that they're now more than DOT_SPACING above the
    // current y can never collide with anything placed from here on (y only decreases).
    while (windowStart < placed.length && placed[windowStart].y - y > DOT_SPACING) windowStart++;
    const searchFrom = Math.max(windowStart, placed.length - MAX_COLLISION_CHECKS);

    const collides = (cx) => {
      for (let i = searchFrom; i < placed.length; i++) {
        const q = placed[i];
        if (Math.hypot(q.x - cx, q.y - y) < DOT_SPACING) return true;
      }
      return false;
    };

    let x = 0;
    // The column only has room for LANES distinct non-overlapping x positions at this y; once
    // the nearby window already holds well more points than that, an exhaustive search is
    // almost certain to fail anyway, so skip straight to the fallback rather than paying for
    // MAX_STEPS*2 doomed collision checks per point in a saturated cluster.
    const nearbyCount = placed.length - searchFrom;
    if (nearbyCount > LANES * 2) {
      x = null;
    } else if (collides(x)) {
      x = null;
      for (let step = 1; step <= MAX_STEPS && x === null; step++) {
        for (const sign of [1, -1]) {
          const candidate = sign * step * SWARM_STEP;
          if (!collides(candidate)) {
            x = candidate;
            break;
          }
        }
      }
    }
    // No free spot within the column's width: rather than pile every overflow point onto one
    // pixel — or snap them onto the same handful of lane positions, which would show up as
    // visible stripes in a saturated cluster — scatter them across the full continuous width
    // via a golden-ratio low-discrepancy sequence, which looks like an organically dense
    // blob instead of a repeating pattern.
    if (x === null) {
      const frac = (placed.length * 0.6180339887498949) % 1;
      x = (frac * 2 - 1) * MAX_HALF_WIDTH_PX;
    }

    p.jitter = Math.max(-1, Math.min(1, x / MAX_HALF_WIDTH_PX));
    placed.push({ x, y });
  }
}

// Lays out just the given points (sets .jitter on each), grouped by channel. Called from
// refreshDerived() with the currently-flagged points, so it reruns whenever the thresholds
// change but never has to consider the full dataset.
function layoutSwarm(points) {
  const byChannel = new Map(CHANNELS.map((c) => [c, []]));
  for (const p of points) byChannel.get(p.channel).push(p);
  for (const channel of CHANNELS) layoutChannelSwarm(byChannel.get(channel));
  return byChannel;
}

// Smoothed per-channel distribution (Gaussian KDE), traced as an outline behind/around the
// swarm so the overall shape still reads even where the swarm itself is one packed blob.
const DENSITY_SAMPLES = 64;

function silvermanBandwidth(sortedValues) {
  const n = sortedValues.length;
  const mean = sortedValues.reduce((a, b) => a + b, 0) / n;
  const variance = sortedValues.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, n - 1);
  const sd = Math.sqrt(variance);
  return sd > 0 ? 1.06 * sd * Math.pow(n, -0.2) : (Y_MAX - Y_MIN) / 20 || 1;
}

function computeDensityCurve(sortedValues) {
  const n = sortedValues.length;
  const h = silvermanBandwidth(sortedValues);
  const cutoff = 4 * h;
  const curve = new Array(DENSITY_SAMPLES + 1);
  let lo = 0;
  let hi = 0;
  for (let i = 0; i <= DENSITY_SAMPLES; i++) {
    const v = Y_MIN + ((Y_MAX - Y_MIN) * i) / DENSITY_SAMPLES;
    while (lo < n && sortedValues[lo] < v - cutoff) lo++;
    while (hi < n && sortedValues[hi] <= v + cutoff) hi++;
    let sum = 0;
    for (let j = lo; j < hi; j++) {
      const u = (v - sortedValues[j]) / h;
      sum += Math.exp(-0.5 * u * u);
    }
    curve[i] = sum / (n * h * Math.sqrt(2 * Math.PI));
  }
  const maxDensity = Math.max(...curve, 1e-9);
  return curve.map((d) => d / maxDensity);
}

const DENSITY_CURVES = new Map(
  CHANNELS.map((channel) => {
    const values = POINTS_BY_CHANNEL.get(channel)
      .map((p) => p.value)
      .sort((a, b) => a - b);
    return [channel, computeDensityCurve(values)];
  }),
);

// A fixed, representative random sample of points shown in green regardless of the current
// thresholds — the full dataset still can't fit as individual dots, but an always-visible
// sample means the chart isn't only ever red. Chosen once via a deterministic hash (not
// Math.random) so the same points are sampled on every render/resize; if a sampled point
// later gets flagged it simply renders red instead (see refreshDerived), it doesn't vanish.
const NORMAL_SAMPLE_SIZE = 1200;

function sampleHash(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

const NORMAL_SAMPLE = new Set();
for (const channel of CHANNELS) {
  const ranked = [...POINTS_BY_CHANNEL.get(channel)].sort(
    (a, b) => sampleHash(`${a.key}|${channel}`) - sampleHash(`${b.key}|${channel}`),
  );
  for (const p of ranked.slice(0, NORMAL_SAMPLE_SIZE)) NORMAL_SAMPLE.add(p);
}

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

const tableViewEl = document.getElementById("table-view");
// row key -> <tr>, so a plain selection click can restyle two rows instead of rebuilding
// every row in the table.
const rowElByKey = new Map();
// The table is collapsed by default and a real run can have tens of thousands of rows, so
// building it (thousands of DOM nodes, one click listener each) is deferred until it's
// actually opened, and skipped on every render in between until something makes it stale.
let tableDirty = true;

function buildTableRows() {
  rowElByKey.clear();
  rowsEl.textContent = "";
  for (const row of sortedRows()) {
    const tr = document.createElement("tr");
    const key = rowKey(row);
    const classes = [];
    if (currentExcludedKeys.has(key)) classes.push("flagged-row");
    if (key === selectedKey) classes.push("row-selected");
    tr.className = classes.join(" ");
    for (const column of TABLE_COLUMNS) {
      const td = document.createElement("td");
      if (column in row.values) {
        const value = row.values[column];
        td.textContent = value;
        if (channelOutOfRange(currentBounds, column, value)) td.classList.add("out-of-range");
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
    rowElByKey.set(key, tr);
  }
  tableDirty = false;
}

function renderTable() {
  for (const th of headerRowEl.children) {
    th.classList.toggle("sorted", th.dataset.column === sortKey);
  }
  if (!tableViewEl.open) {
    tableDirty = true;
    return;
  }
  buildTableRows();
}

// Cheap path for a plain selection click: only the previously/newly selected row's class
// actually changes, so touch just those two <tr> elements instead of rebuilding the table.
function updateTableSelection(previousKey) {
  if (tableDirty || !tableViewEl.open) return;
  const prevEl = previousKey && rowElByKey.get(previousKey);
  if (prevEl) prevEl.classList.remove("row-selected");
  const nextEl = selectedKey && rowElByKey.get(selectedKey);
  if (nextEl) nextEl.classList.add("row-selected");
}

tableViewEl.addEventListener("toggle", () => {
  if (tableViewEl.open && tableDirty) buildTableRows();
});

function selectRow(row) {
  const previousKey = selectedKey;
  selectedKey = rowKey(row);

  previewImageWrap.textContent = "";
  const thumb = row.hasThumb ? THUMBS.get(rowKey(row)) : null;
  if (thumb) {
    const img = thumb.cloneNode();
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
  updateTableSelection(previousKey);
}

function resizeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  const rect = chartWrap.getBoundingClientRect();
  const cssHeight = canvas.clientHeight || CHART_HEIGHT;
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
  const textSecondary = cssVar("--text-secondary");
  const textPrimary = cssVar("--text-primary");

  const plotW = Math.max(1, width - MARGIN_LEFT - MARGIN_RIGHT);
  const plotH = Math.max(1, height - MARGIN_TOP - MARGIN_BOTTOM);
  const bandW = plotW / CHANNELS.length;

  const yScale = (value) => MARGIN_TOP + plotH * (1 - (value - Y_MIN) / (Y_MAX - Y_MIN));
  const xCenter = (channelIndex) => MARGIN_LEFT + bandW * (channelIndex + 0.5);

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
    ctx.moveTo(MARGIN_LEFT, y);
    ctx.lineTo(MARGIN_LEFT + plotW, y);
    ctx.stroke();
    ctx.fillText(value.toFixed(1), MARGIN_LEFT - 8, y);
  }

  ctx.strokeStyle = cssVar("--baseline");
  ctx.beginPath();
  const baselineY = Math.round(MARGIN_TOP + plotH) + 0.5;
  ctx.moveTo(MARGIN_LEFT, baselineY);
  ctx.lineTo(MARGIN_LEFT + plotW, baselineY);
  ctx.stroke();

  ctx.fillStyle = textPrimary;
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.font = "12px system-ui, sans-serif";
  CHANNELS.forEach((channel, i) => {
    ctx.fillText(channel, xCenter(i), MARGIN_TOP + plotH + 8);
  });

  // Density outline path for one channel: a mirrored silhouette of its KDE curve, traced
  // twice below (once as a soft fill behind the swarm, once as a crisp stroke on top of it
  // so the shape survives however densely packed the swarm gets).
  function traceDensityPath(channelIdx) {
    const curve = DENSITY_CURVES.get(CHANNELS[channelIdx]);
    const cx = xCenter(channelIdx);
    const halfWidth = bandW * SWARM_MAX_FRACTION;
    ctx.beginPath();
    for (let i = 0; i <= DENSITY_SAMPLES; i++) {
      const value = Y_MIN + ((Y_MAX - Y_MIN) * i) / DENSITY_SAMPLES;
      const y = yScale(value);
      const x = cx - curve[i] * halfWidth;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    for (let i = DENSITY_SAMPLES; i >= 0; i--) {
      const value = Y_MIN + ((Y_MAX - Y_MIN) * i) / DENSITY_SAMPLES;
      ctx.lineTo(cx + curve[i] * halfWidth, yScale(value));
    }
    ctx.closePath();
  }

  ctx.fillStyle = muted;
  ctx.globalAlpha = 0.14;
  CHANNELS.forEach((_, i) => {
    traceDensityPath(i);
    ctx.fill();
  });
  ctx.globalAlpha = 1;

  const channelIndex = Object.fromEntries(CHANNELS.map((c, i) => [c, i]));
  // The full dataset can't fit as individual marks (see layoutSwarm above), so what's drawn
  // is every currently-flagged image (red — the set actually worth clicking through) plus a
  // fixed representative sample of everything else (green), so the chart isn't only ever red
  // and still conveys where the bulk of "normal" images sits.
  for (const p of currentDisplayedPoints) {
    const cx = xCenter(channelIndex[p.channel]) + p.jitter * (bandW * SWARM_MAX_FRACTION);
    const cy = yScale(p.value);
    const flagged = currentExcludedKeys.has(p.key);

    ctx.beginPath();
    ctx.arc(cx, cy, DOT_RADIUS, 0, Math.PI * 2);
    ctx.fillStyle = flagged ? critical : good;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = surface;
    ctx.stroke();

    if (p.key === selectedKey) {
      ctx.beginPath();
      ctx.arc(cx, cy, DOT_RADIUS + 3, 0, Math.PI * 2);
      ctx.lineWidth = 2;
      ctx.strokeStyle = textPrimary;
      ctx.stroke();
    }
  }

  // Retraced on top of the dots so the outline's shape is never fully buried, but at partial
  // opacity so dots sitting right on the boundary still show through it.
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = textSecondary;
  ctx.globalAlpha = 0.55;
  CHANNELS.forEach((_, i) => {
    traceDensityPath(i);
    ctx.stroke();
  });
  ctx.globalAlpha = 1;

  plotBounds = {
    marginLeft: MARGIN_LEFT,
    marginTop: MARGIN_TOP,
    plotW,
    plotH,
    bandW,
    yScale,
    channelIndex,
    width,
    height,
  };
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
  for (const p of displayedPointsByChannel.get(channel)) {
    const cx = xCenter + p.jitter * (bandW * SWARM_MAX_FRACTION);
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
  refreshDerived();
  summaryEl.textContent = `${currentExcludedKeys.size} of ${ROWS.length} images currently flagged`;
  redrawChart();
  renderTable();
}

function csvEscape(value) {
  const text = String(value);
  return /[",\\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadExclusions() {
  const excluded = ROWS.filter((row) => currentExcludedKeys.has(rowKey(row)));
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
// renderAll() populates currentBounds/currentExcludedKeys before resizeCanvas() does the
// page's one real chart draw; redrawChart() inside renderAll() is a no-op this first time
// since plotBounds isn't set until resizeCanvas() runs.
renderAll();
resizeCanvas();
</script>
</body>
</html>
"""
