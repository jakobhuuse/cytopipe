"""Self-contained HTML gallery for manually reviewing per-image QC metrics."""

import base64
import json
from pathlib import Path

import pandas as pd

from cytopipe.columns import METADATA_PLATE, METADATA_SITE, METADATA_WELL

from .scan import (
    BLUR_PREFIX,
    CELL_COUNT_COLUMN,
    FOCUS_SCORE_PREFIX,
    PERCENT_MAXIMAL_PREFIX,
    channel_columns,
)

CELL_COUNT_CHANNEL = "Nuclei"


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


def _panel_defs(metrics: pd.DataFrame) -> list[dict]:
    """The four metric panels the gallery can plot, each a threshold mode plus a channel ->
    source-column mapping. Cell count has a single synthetic "channel" (there's one count per
    image, not one per fluorescence channel) so the rest of the gallery can treat every panel
    uniformly as "one or more channels" rather than special-casing it. ``shortLabel`` names the
    per-channel table column ("Blur AGP") since ``label`` alone would collide across panels
    that share channel names.
    """
    return [
        {
            "key": "blur",
            "label": "Blur score",
            "shortLabel": "Blur",
            "thresholdMode": "range",
            "columns": channel_columns(metrics, BLUR_PREFIX),
            # PowerLogLogSlope has no natural floor/ceiling, so let the axis follow the data.
            "domainFloor": None,
            "domainCeiling": None,
        },
        {
            "key": "cellCount",
            "label": "Cell count",
            "shortLabel": "Cell count",
            "thresholdMode": "range",
            "columns": {CELL_COUNT_CHANNEL: CELL_COUNT_COLUMN},
            "domainFloor": 0,  # a count can't go negative
            "domainCeiling": None,
        },
        {
            "key": "percentMaximal",
            "label": "Percent maximal",
            "shortLabel": "Max%",
            "thresholdMode": "max",
            "columns": channel_columns(metrics, PERCENT_MAXIMAL_PREFIX),
            "domainFloor": 0,  # a fraction of pixels can't be negative or exceed all of them
            "domainCeiling": 1,
        },
        {
            "key": "focusScore",
            "label": "Focus score",
            "shortLabel": "Focus",
            "thresholdMode": "range",
            "columns": channel_columns(metrics, FOCUS_SCORE_PREFIX),
            "domainFloor": 0,  # CellProfiler's FocusScore is a non-negative variance measure
            "domainCeiling": None,
        },
    ]


def build_gallery(metrics: pd.DataFrame, out_html: Path) -> Path:
    """Write a self-contained HTML review gallery to ``out_html`` and return the path.

    Embeds four metric panels (blur score, cell count, percent maximal, focus score) as a JSON
    blob, one value per channel per panel per image, together with a threshold input per
    channel per panel (starting empty/unbounded, max-only for percent maximal). An image is
    flagged if it violates any panel's threshold, not only the panel currently on screen. Each
    channel renders as a histogram (binned over every image, not a sample); clicking a bucket
    opens a random sample of its images for inspection.
    """
    panels = _panel_defs(metrics)

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
                "values": {
                    panel["key"]: {
                        channel: row[column] for channel, column in panel["columns"].items()
                    }
                    for panel in panels
                },
            }
        )
        if overlay_path is not None:
            key = _row_key(plate, well, site)
            thumb_tags.append(f'<img data-key="{key}" src="{_thumbnail_data_uri(overlay_path)}">')

    panels_json = [
        {
            "key": panel["key"],
            "label": panel["label"],
            "shortLabel": panel["shortLabel"],
            "thresholdMode": panel["thresholdMode"],
            "channels": sorted(panel["columns"]),
            "domainFloor": panel["domainFloor"],
            "domainCeiling": panel["domainCeiling"],
        }
        for panel in panels
    ]

    document = (
        _HTML_TEMPLATE.replace("__PANELS_JSON__", json.dumps(panels_json))
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

  #panel-tabs { display: flex; gap: 0.35rem; margin: 1.25rem 0 0; }
  .panel-tab {
    padding: 0.45rem 0.85rem; border-radius: 6px 6px 0 0; border: 1px solid var(--border);
    border-bottom: none; background: var(--page); color: var(--text-secondary); cursor: pointer;
    font: inherit; font-size: 0.85rem; font-weight: 600;
  }
  .panel-tab[aria-selected="true"] { background: var(--surface-1); color: var(--text-primary); }

  #controls {
    display: flex; flex-wrap: wrap; gap: 1rem; align-items: end;
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 0 8px 8px 8px;
    padding: 0.75rem 1rem; margin: 0 0 1rem;
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
  .legend .swatch.line {
    background: none; border-top: 2px solid var(--critical); border-radius: 0; width: 10px;
  }
  #download {
    margin-left: auto; padding: 0.5rem 1rem; border-radius: 6px; border: 1px solid var(--border);
    background: var(--surface-1); color: var(--text-primary); cursor: pointer;
    font-weight: 600; font: inherit;
  }
  #download:hover { background: var(--page); }

  #chart-card {
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 8px; padding: 1rem;
  }
  #chart-wrap { position: relative; width: 100%; }
  canvas#chart { width: 100%; height: 360px; display: block; cursor: default; }

  #tooltip {
    position: absolute; pointer-events: none;
    background: var(--text-primary); color: var(--surface-1);
    font-size: 0.75rem; padding: 0.3rem 0.5rem; border-radius: 4px;
    transform: translate(-50%, -125%);
    white-space: nowrap; opacity: 0; transition: opacity 0.1s;
  }
  #tooltip .value { font-weight: 700; margin-right: 0.35rem; }
  #tooltip .meta { opacity: 0.85; }

  #inspection-card {
    display: flex; gap: 1.25rem; align-items: flex-start; flex-wrap: wrap; margin-top: 1.25rem;
  }
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

  #table-section {
    flex: 1 1 640px; min-width: 320px;
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 8px; padding: 1rem;
  }
  #table-toolbar { margin-bottom: 0.75rem; }
  #table-search {
    width: 100%; max-width: 320px; background: var(--page); color: var(--text-primary);
    border: 1px solid var(--border); border-radius: 6px; padding: 0.4rem 0.6rem; font: inherit;
  }
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

  #bucket-modal {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5);
    display: flex; align-items: center; justify-content: center; z-index: 100; padding: 1.5rem;
  }
  #bucket-modal[hidden] { display: none; }
  #bucket-modal-content {
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
    padding: 1.25rem; max-width: 640px; width: 100%; max-height: 85vh; overflow-y: auto;
  }
  #bucket-modal-header {
    display: flex; justify-content: space-between; align-items: center; gap: 1rem;
    margin-bottom: 0.75rem;
  }
  #bucket-modal-header h2 { font-size: 0.95rem; margin: 0; font-weight: 600; }
  #bucket-modal-close {
    border: none; background: none; color: var(--text-secondary); font-size: 1.25rem;
    cursor: pointer; line-height: 1; padding: 0.25rem;
  }
  #bucket-modal-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.6rem; }
  .bucket-cell {
    display: flex; flex-direction: column; gap: 0.3rem; border: 1px solid var(--border);
    background: var(--page); border-radius: 6px; padding: 0.35rem; cursor: pointer;
    font: inherit; color: var(--text-primary);
  }
  .bucket-cell img {
    width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 4px; display: block;
  }
  .bucket-cell-empty {
    aspect-ratio: 1; display: flex; align-items: center; justify-content: center;
    color: var(--muted); font-size: 0.7rem; background: var(--page); border-radius: 4px;
  }
  .bucket-cell-caption { font-size: 0.7rem; color: var(--text-secondary); text-align: center; }
</style>
</head>
<body>
<h1>QC image review</h1>
<p class="hint">
  Each tab is a metric panel; each column within it is a channel, plotted as a histogram over
  every image (not a sample), split red/green by how many of a bucket's images are currently
  flagged. Set a min (where available) and max per channel to flag images by eye, a red line
  marks each active cutoff. An image's dots turn red on every panel and channel, not only the
  one that tripped a threshold, since a flagged image gets excluded outright, not one metric of
  it, and thresholds on every panel stay active even while you're looking at a different one.
  Click a bucket to open a random sample of its images; click one to load it into the inspection
  panel below, alongside the searchable table. When satisfied, click &quot;Download exclusion
  list&quot; to save a CSV of the flagged Plate/Well/Site rows, then point
  <code>--qc_exclude_file</code> at that file.
</p>

<div id="panel-tabs" role="tablist"></div>
<div id="controls"></div>

<div id="summary-row">
  <span id="summary"></span>
  <span class="legend">
    <span><span class="swatch good"></span>Normal</span>
    <span><span class="swatch critical"></span>Flagged</span>
    <span><span class="swatch line"></span>Cutoff</span>
  </span>
  <button id="download" type="button">Download exclusion list</button>
</div>

<div id="chart-card">
  <div id="chart-wrap">
    <canvas id="chart"></canvas>
    <div id="tooltip"><span class="value"></span><span class="meta"></span></div>
  </div>
</div>

<div id="inspection-card">
  <div id="preview-card">
    <h2>Selected image</h2>
    <div id="preview-image-wrap">
      <span>Click a bucket, then an image, to inspect it here</span>
    </div>
    <dl id="preview-meta"></dl>
  </div>
  <div id="table-section">
    <div id="table-toolbar">
      <input id="table-search" type="search" placeholder="Search plate, well, site, or value">
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
  </div>
</div>

<div id="bucket-modal" hidden role="dialog" aria-modal="true">
  <div id="bucket-modal-content">
    <div id="bucket-modal-header">
      <h2 id="bucket-modal-title"></h2>
      <button id="bucket-modal-close" type="button" aria-label="Close">&times;</button>
    </div>
    <div id="bucket-modal-grid"></div>
  </div>
</div>

<!--
  Thumbnails live here, outside the ROWS array below: the HTML parser streams plain markup
  cheaply, whereas the JS engine would have to fully materialize every thumbnail as a live
  string object before the page could do anything if they sat in ROWS instead, which is what
  used to make real (multi-plate, tens-of-thousands-of-image) runs unusable. Looked up by
  plate|well|site key and cloned into the preview pane (or a bucket's gallery cell) only when
  asked for, never eagerly for every image up front.
-->
<div id="thumb-store" hidden>__THUMBS_HTML__</div>

<script>
const PANELS = __PANELS_JSON__;
const ROWS = __ROWS_JSON__;

const panelTabsEl = document.getElementById("panel-tabs");
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
const searchInputEl = document.getElementById("table-search");
const headerRowEl = document.getElementById("header-row");
const rowsEl = document.getElementById("rows");
const tableCountEl = document.getElementById("table-count");
const modalEl = document.getElementById("bucket-modal");
const modalTitleEl = document.getElementById("bucket-modal-title");
const modalGridEl = document.getElementById("bucket-modal-grid");
const modalCloseEl = document.getElementById("bucket-modal-close");

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function rowKey(row) {
  return row.plate + "|" + row.well + "|" + row.site;
}

function formatMetricValue(panelKey, value) {
  return panelKey === "cellCount" ? String(value) : value.toFixed(3);
}

// Chart geometry. Canvas height is fixed via CSS (640px) while width responds to the window,
// so bars/lines are recomputed fresh at draw time against whatever width resizeCanvas reports.
const MARGIN_LEFT = 12;
const MARGIN_RIGHT = 12;
const MARGIN_TOP = 16;
const MARGIN_BOTTOM = 8;
const ROW_HEIGHT = 210; // bar area, per channel
const ROW_LABEL_HEIGHT = 40; // x-axis ticks + channel name, per channel
const ROW_GAP = 20; // extra breathing room between one channel's label and the next's bars
const ROW_HEADROOM_FRACTION = 0.08; // keeps the tallest bar from touching the row's top edge
const MIN_BAR_PX = 2; // keeps a single-image bucket visible instead of a sub-pixel sliver
const BIN_COUNT = 60;
const GALLERY_SIZE = 16; // a 4x4 grid

// Reads one min/max input. Returns null for a side a panel doesn't have (percent maximal has
// no "min") without querying a nonexistent element.
function currentBound(panelKey, channel, side) {
  const el = document.getElementById(`range-${panelKey}-${channel}-${side}`);
  if (!el) return null;
  const value = el.value.trim();
  return value === "" ? null : Number(value);
}

// Reads every min/max input on every panel once per render pass, not just the panel on
// screen, since an image is flagged for violating any panel's threshold, seen or not. This
// runs once per filter change; channelOutOfRange/rowExcluded run per row (or per row per
// channel) over up to tens of thousands of rows, so paying the DOM lookups down here instead
// keeps those hot loops to plain object access.
function computeBounds() {
  const bounds = {};
  for (const panel of PANELS) {
    const panelBounds = {};
    for (const channel of panel.channels) {
      const high = currentBound(panel.key, channel, "max");
      const low = panel.thresholdMode === "range" ? currentBound(panel.key, channel, "min") : null;
      panelBounds[channel] = [low, high];
    }
    bounds[panel.key] = panelBounds;
  }
  return bounds;
}

function channelOutOfRange(bounds, panelKey, channel, value) {
  const [low, high] = bounds[panelKey][channel];
  return (low !== null && value < low) || (high !== null && value > high);
}

function rowExcluded(bounds, row) {
  return PANELS.some((panel) =>
    panel.channels.some((channel) =>
      channelOutOfRange(bounds, panel.key, channel, row.values[panel.key][channel]),
    ),
  );
}

// floor/ceiling clamp the padded domain to a metric's natural bounds (a count can't go
// negative, a fraction-of-pixels metric can't exceed 1), so the axis never shows a value the
// metric could never actually take just because padding pushed past it.
function valueDomain(points, floor, ceiling) {
  let min = Infinity;
  let max = -Infinity;
  for (const p of points) {
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
  let domainMin = min - pad;
  let domainMax = max + pad;
  if (floor !== null && floor !== undefined) domainMin = Math.max(domainMin, floor);
  if (ceiling !== null && ceiling !== undefined) domainMax = Math.min(domainMax, ceiling);
  return [domainMin, domainMax];
}

// Bins a channel's points into BIN_COUNT equal-width buckets across [yMin, yMax], keeping each
// bucket's actual row list (not just a count) so a click can sample real images from it.
function computeBins(points, yMin, yMax) {
  const span = yMax - yMin || 1;
  const bins = [];
  for (let i = 0; i < BIN_COUNT; i++) {
    bins.push({
      lower: yMin + (span * i) / BIN_COUNT,
      upper: yMin + (span * (i + 1)) / BIN_COUNT,
      rows: [],
      flaggedCount: 0,
    });
  }
  for (const p of points) {
    const raw = Math.floor(((p.value - yMin) / span) * BIN_COUNT);
    const idx = Math.min(BIN_COUNT - 1, Math.max(0, raw));
    bins[idx].rows.push(p.row);
  }
  return bins;
}

// Everything one panel needs to plot itself: its own points (one per row per channel, since
// different panels measure different things), its own value domain, and its own bins (which
// depend only on the data, not on thresholds, so computed once and reused).
function buildPanelState(panel) {
  const points = [];
  const pointsByChannel = new Map(panel.channels.map((c) => [c, []]));
  for (const row of ROWS) {
    const key = rowKey(row);
    for (const channel of panel.channels) {
      const point = { row, channel, key, value: row.values[panel.key][channel] };
      points.push(point);
      pointsByChannel.get(channel).push(point);
    }
  }

  const [yMin, yMax] = valueDomain(points, panel.domainFloor, panel.domainCeiling);
  const binsByChannel = new Map(
    panel.channels.map((channel) => {
      const channelPoints = pointsByChannel.get(channel);
      return [channel, computeBins(channelPoints, yMin, yMax)];
    }),
  );

  return { panel, points, pointsByChannel, yMin, yMax, binsByChannel };
}

const PANEL_STATE = new Map(PANELS.map((panel) => [panel.key, buildPanelState(panel)]));

let activePanelKey = PANELS[0].key;

// Thumbnails, keyed by plate|well|site; populated from the hidden markup, never from ROWS.
const THUMBS = new Map();
for (const img of document.querySelectorAll("#thumb-store img")) {
  THUMBS.set(img.dataset.key, img);
}

let selectedKey = null;
let plotBounds = null;

function buildPanelTabs() {
  for (const panel of PANELS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "panel-tab";
    btn.textContent = panel.label;
    btn.dataset.panel = panel.key;
    btn.setAttribute("aria-selected", String(panel.key === activePanelKey));
    btn.addEventListener("click", () => setActivePanel(panel.key));
    panelTabsEl.append(btn);
  }
}

function setActivePanel(panelKey) {
  if (panelKey === activePanelKey) return;
  activePanelKey = panelKey;
  for (const btn of panelTabsEl.children) {
    btn.setAttribute("aria-selected", String(btn.dataset.panel === panelKey));
  }
  for (const group of controlsEl.children) {
    group.style.display = group.dataset.panel === panelKey ? "contents" : "none";
  }
  refreshActivePanelBinCounts();
  plotBounds = null;
  resizeCanvas();
}

// display:contents when active so its channel-range children flow directly into #controls'
// flex row as if there were no wrapper; display:none (not the "hidden" attribute, which would
// fight that same inline style) when a different panel is active.
function buildControls() {
  for (const panel of PANELS) {
    const group = document.createElement("div");
    group.className = "panel-controls";
    group.dataset.panel = panel.key;
    group.style.display = panel.key === activePanelKey ? "contents" : "none";
    for (const channel of panel.channels) {
      const wrap = document.createElement("div");
      wrap.className = "channel-range";
      const label = document.createElement("strong");
      label.textContent = channel;
      const inputs = document.createElement("div");
      inputs.className = "inputs";
      if (panel.thresholdMode === "range") {
        const minInput = document.createElement("input");
        minInput.type = "number";
        minInput.step = "any";
        minInput.placeholder = "min";
        minInput.id = `range-${panel.key}-${channel}-min`;
        minInput.addEventListener("input", renderAll);
        inputs.append(minInput, document.createTextNode(" - "));
      }
      const maxInput = document.createElement("input");
      maxInput.type = "number";
      maxInput.step = "any";
      maxInput.placeholder = "max";
      maxInput.id = `range-${panel.key}-${channel}-max`;
      maxInput.addEventListener("input", renderAll);
      inputs.append(maxInput);
      wrap.append(label, inputs);
      group.append(wrap);
    }
    controlsEl.append(group);
  }
}

// Every per-channel metric column across every panel, in tab order, each with a stable
// "panel:channel" identity (plain channel names collide across panels, e.g. "AGP" is both a
// blur and a focus-score channel) and a short label for the table header.
const METRIC_COLUMNS = PANELS.flatMap((panel) =>
  panel.channels.map((channel) => ({
    panelKey: panel.key,
    channel,
    label: panel.channels.length > 1 ? `${panel.shortLabel} ${channel}` : panel.shortLabel,
  })),
);
const META_COLUMNS = ["plate", "well", "site"];
const META_LABELS = { plate: "Plate", well: "Well", site: "Site" };

let sortColumnId = null;
let sortValueFn = null;
let sortAsc = true;

function buildTableHeader() {
  const addColumn = (id, label, valueFn) => {
    const th = document.createElement("th");
    th.textContent = label;
    th.dataset.columnId = id;
    th.addEventListener("click", () => {
      sortAsc = sortColumnId === id ? !sortAsc : true;
      sortColumnId = id;
      sortValueFn = valueFn;
      renderTable();
    });
    headerRowEl.append(th);
  };
  for (const column of META_COLUMNS) {
    addColumn(`meta:${column}`, META_LABELS[column], (row) => row[column]);
  }
  for (const metric of METRIC_COLUMNS) {
    addColumn(
      `metric:${metric.panelKey}:${metric.channel}`,
      metric.label,
      (row) => row.values[metric.panelKey][metric.channel],
    );
  }
  const imageTh = document.createElement("th");
  imageTh.textContent = "Image";
  headerRowEl.append(imageTh);
}

// Search matches plate/well/site or any panel's channel value, as plain substring text, so
// "A02" or "-2.3" both work without needing a per-column search UI.
let searchQuery = "";

function rowMatchesSearch(row) {
  if (!searchQuery) return true;
  if (String(row.plate).toLowerCase().includes(searchQuery)) return true;
  if (String(row.well).toLowerCase().includes(searchQuery)) return true;
  if (String(row.site).toLowerCase().includes(searchQuery)) return true;
  return METRIC_COLUMNS.some((metric) =>
    String(row.values[metric.panelKey][metric.channel]).toLowerCase().includes(searchQuery),
  );
}

function visibleRows() {
  const matching = searchQuery ? ROWS.filter(rowMatchesSearch) : ROWS;
  if (!sortColumnId) return matching;
  return [...matching].sort((a, b) => {
    const av = sortValueFn(a);
    const bv = sortValueFn(b);
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortAsc ? cmp : -cmp;
  });
}

let searchDebounce = null;
searchInputEl.addEventListener("input", () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    searchQuery = searchInputEl.value.trim().toLowerCase();
    renderTable();
  }, 150);
});

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
  const rows = visibleRows();
  for (const row of rows) {
    const tr = document.createElement("tr");
    const key = rowKey(row);
    const classes = [];
    if (currentExcludedKeys.has(key)) classes.push("flagged-row");
    if (key === selectedKey) classes.push("row-selected");
    tr.className = classes.join(" ");

    for (const column of META_COLUMNS) {
      const td = document.createElement("td");
      td.textContent = row[column];
      tr.append(td);
    }
    for (const metric of METRIC_COLUMNS) {
      const td = document.createElement("td");
      const value = row.values[metric.panelKey][metric.channel];
      td.textContent = value;
      if (channelOutOfRange(currentBounds, metric.panelKey, metric.channel, value)) {
        td.classList.add("out-of-range");
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
  tableCountEl.textContent = searchQuery ? `${rows.length} of ${ROWS.length}` : String(ROWS.length);
  tableDirty = false;
}

function renderTable() {
  for (const th of headerRowEl.children) {
    th.classList.toggle("sorted", th.dataset.columnId === sortColumnId);
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
    ...METRIC_COLUMNS.map((metric) => [
      metric.label,
      formatMetricValue(metric.panelKey, row.values[metric.panelKey][metric.channel]),
    ]),
  ];
  for (const [label, value] of entries) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    previewMetaEl.append(dt, dd);
  }

  updateTableSelection(previousKey);
}

// Partial Fisher-Yates: picks up to n random, non-repeating items from array without
// disturbing the caller's copy or needing a full shuffle of a possibly large bucket.
function sampleRandom(array, n) {
  const copy = [...array];
  const count = Math.min(n, copy.length);
  for (let i = 0; i < count; i++) {
    const j = i + Math.floor(Math.random() * (copy.length - i));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy.slice(0, count);
}

function openBucketModal(channel, bin) {
  const sample = sampleRandom(bin.rows, GALLERY_SIZE);
  modalTitleEl.textContent =
    `${channel}: ${bin.lower.toFixed(2)}–${bin.upper.toFixed(2)} ` +
    `(${bin.rows.length} images, ${bin.flaggedCount} flagged)`;
  modalGridEl.textContent = "";
  for (const row of sample) {
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "bucket-cell";
    const thumb = row.hasThumb ? THUMBS.get(rowKey(row)) : null;
    if (thumb) {
      const img = thumb.cloneNode();
      img.alt = `${row.plate} ${row.well} site ${row.site}`;
      cell.append(img);
    } else {
      const span = document.createElement("span");
      span.className = "bucket-cell-empty";
      span.textContent = "No image";
      cell.append(span);
    }
    const caption = document.createElement("span");
    caption.className = "bucket-cell-caption";
    caption.textContent = `${row.well} · site ${row.site}`;
    cell.append(caption);
    cell.addEventListener("click", () => {
      selectRow(row);
      closeBucketModal();
    });
    modalGridEl.append(cell);
  }
  modalEl.hidden = false;
}

function closeBucketModal() {
  modalEl.hidden = true;
}

modalCloseEl.addEventListener("click", closeBucketModal);
modalEl.addEventListener("click", (evt) => {
  if (evt.target === modalEl) closeBucketModal();
});
window.addEventListener("keydown", (evt) => {
  if (evt.key === "Escape" && !modalEl.hidden) closeBucketModal();
});

// Recomputed once whenever a range input changes, then reused as-is by chart/table redraws
// that only a selection click (not a filter change) triggers.
let currentBounds = null;
let currentExcludedKeys = null;

// Bucket membership (which rows fall in which bucket) never changes, only how many of a
// bucket's rows are currently flagged does, so only the flagged counts get recomputed here
// and only for the panel actually on screen.
function refreshActivePanelBinCounts() {
  const state = PANEL_STATE.get(activePanelKey);
  for (const channel of state.panel.channels) {
    for (const bin of state.binsByChannel.get(channel)) {
      let count = 0;
      for (const row of bin.rows) {
        if (currentExcludedKeys.has(rowKey(row))) count++;
      }
      bin.flaggedCount = count;
    }
  }
}

function refreshDerived() {
  currentBounds = computeBounds();
  currentExcludedKeys = new Set(ROWS.filter((row) => rowExcluded(currentBounds, row)).map(rowKey));
  refreshActivePanelBinCounts();
}

// Channels stack vertically (one full-width histogram per row) rather than sitting side by
// side, so each one gets the full width to pan out into more, finer buckets. Total height
// scales with however many channels the active panel has (1 for cell count, 5 for the rest).
function chartHeightFor(channelCount) {
  return MARGIN_TOP + channelCount * (ROW_HEIGHT + ROW_LABEL_HEIGHT + ROW_GAP) + MARGIN_BOTTOM;
}

function resizeCanvas() {
  const state = PANEL_STATE.get(activePanelKey);
  const cssHeight = chartHeightFor(state.panel.channels.length);
  canvas.style.height = `${cssHeight}px`;
  const dpr = window.devicePixelRatio || 1;
  const rect = chartWrap.getBoundingClientRect();
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  drawChart(rect.width, cssHeight);
}

function redrawChart() {
  if (plotBounds) drawChart(plotBounds.width, plotBounds.height);
}

// One channel's histogram: standard orientation (value on x, count on y, bars rising from a
// baseline), like any matplotlib/plotly histogram, not the mirrored/rotated layout this used
// to have. Channels stack one per row rather than sitting side by side, so each gets the full
// width to pan its value range out into more, finer buckets instead of being squeezed into a
// narrow column; a shared x domain per channel still lets them share one canvas and one
// resize/click/hover code path.
function drawChart(width, height) {
  const state = PANEL_STATE.get(activePanelKey);
  const channels = state.panel.channels;
  const domainMin = state.yMin;
  const domainMax = state.yMax;

  const good = cssVar("--good");
  const critical = cssVar("--critical");
  const surface = cssVar("--surface-1");
  const muted = cssVar("--muted");
  const textPrimary = cssVar("--text-primary");

  const xLeft = MARGIN_LEFT;
  const xRight = Math.max(xLeft + 1, width - MARGIN_RIGHT);
  const rowStride = ROW_HEIGHT + ROW_LABEL_HEIGHT + ROW_GAP;

  ctx.clearRect(0, 0, width, height);

  const subplots = channels.map((channel, i) => {
    const rowTop = MARGIN_TOP + i * rowStride;
    const rowBottom = rowTop + ROW_HEIGHT;
    const bins = state.binsByChannel.get(channel);
    const maxCount = Math.max(1, ...bins.map((b) => b.rows.length));
    const domainSpan = domainMax - domainMin;
    const xScale = (value) => xLeft + ((value - domainMin) / domainSpan) * (xRight - xLeft);
    // Usable height stops short of the row's top edge (headroom) so even the tallest bucket
    // has visible clearance above it instead of touching/looking clipped by the row boundary.
    const usableHeight = ROW_HEIGHT * (1 - ROW_HEADROOM_FRACTION);
    const countScale = (count) => rowBottom - (count / maxCount) * usableHeight;
    return { channel, xLeft, xRight, rowTop, rowBottom, bins, xScale, countScale };
  });

  for (const sub of subplots) {
    // Baseline (the histogram's own x-axis line).
    ctx.strokeStyle = cssVar("--baseline");
    ctx.lineWidth = 1;
    ctx.beginPath();
    const baselineY = Math.round(sub.rowBottom) + 0.5;
    ctx.moveTo(sub.xLeft, baselineY);
    ctx.lineTo(sub.xRight, baselineY);
    ctx.stroke();

    // Bars: contiguous, no gaps between adjacent buckets, as in a standard histogram. Each
    // bar stacks its flagged count (red) on top of its normal count (green), so composition
    // reads directly from the bar instead of needing the two colors overlaid. The whole bar
    // is clamped to a minimum height so a bucket with just one or two images next to a much
    // taller one stays visible instead of rounding down to a sub-pixel sliver; the red/green
    // split still reflects the bucket's true flagged fraction within whatever height it gets.
    for (const bin of sub.bins) {
      if (bin.rows.length === 0) continue;
      const barLeft = sub.xScale(bin.lower);
      const barRight = sub.xScale(bin.upper);
      const naturalTopY = sub.countScale(bin.rows.length);
      const topY = Math.min(naturalTopY, sub.rowBottom - MIN_BAR_PX);
      const barHeight = sub.rowBottom - topY;
      const flaggedHeight = barHeight * (bin.flaggedCount / bin.rows.length);
      ctx.fillStyle = good;
      ctx.fillRect(barLeft, topY, barRight - barLeft, barHeight - flaggedHeight);
      if (bin.flaggedCount > 0) {
        const flaggedTopY = topY + (barHeight - flaggedHeight);
        ctx.fillStyle = critical;
        ctx.fillRect(barLeft, flaggedTopY, barRight - barLeft, flaggedHeight);
      }
    }

    // x-axis value ticks (more of them now that each channel spans the full width).
    ctx.fillStyle = muted;
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const tickCount = 8;
    for (let i = 0; i <= tickCount; i++) {
      const value = domainMin + ((domainMax - domainMin) * i) / tickCount;
      ctx.fillText(value.toFixed(1), sub.xScale(value), sub.rowBottom + 6);
    }

    // Channel name below the ticks.
    ctx.fillStyle = textPrimary;
    ctx.font = "12px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(sub.channel, sub.xLeft, sub.rowBottom + 20);

    // Cutoff lines: a pale halo behind a bold, near-black/white line, so the cutoff itself
    // reads clearly regardless of whether it falls over a green bar, a red (flagged) bar, or
    // empty space, rather than the red line blending into the red flagged segments it marks.
    const [low, high] = currentBounds[state.panel.key][sub.channel];
    for (const bound of [low, high]) {
      if (bound === null) continue;
      const x = Math.round(sub.xScale(bound)) + 0.5;
      ctx.strokeStyle = surface;
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(x, sub.rowTop);
      ctx.lineTo(x, sub.rowBottom);
      ctx.stroke();
      ctx.strokeStyle = textPrimary;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x, sub.rowTop);
      ctx.lineTo(x, sub.rowBottom);
      ctx.stroke();
    }
  }

  plotBounds = { subplots, width, height };
}

// Which channel/bucket a canvas position falls in, or null if it's outside every row.
function binAt(mx, my) {
  if (!plotBounds) return null;
  for (const sub of plotBounds.subplots) {
    if (my < sub.rowTop || my > sub.rowBottom) continue;
    if (mx < sub.xLeft || mx > sub.xRight) continue;
    for (const bin of sub.bins) {
      const barLeft = sub.xScale(bin.lower);
      const barRight = sub.xScale(bin.upper);
      if (mx >= barLeft && mx <= barRight) return { channel: sub.channel, bin };
    }
  }
  return null;
}

function eventPoint(evt) {
  const rect = canvas.getBoundingClientRect();
  return [evt.clientX - rect.left, evt.clientY - rect.top];
}

canvas.addEventListener("pointermove", (evt) => {
  const [mx, my] = eventPoint(evt);
  const hit = binAt(mx, my);
  if (hit) {
    tooltipEl.style.opacity = "1";
    tooltipEl.style.left = `${mx}px`;
    tooltipEl.style.top = `${my}px`;
    tooltipValueEl.textContent = `${hit.bin.rows.length}`;
    tooltipMetaEl.textContent =
      `${hit.channel} · ${hit.bin.lower.toFixed(2)}–${hit.bin.upper.toFixed(2)} ` +
      `(${hit.bin.flaggedCount} flagged)`;
    canvas.style.cursor = hit.bin.rows.length > 0 ? "pointer" : "default";
  } else {
    tooltipEl.style.opacity = "0";
    canvas.style.cursor = "default";
  }
});

canvas.addEventListener("pointerleave", () => {
  tooltipEl.style.opacity = "0";
});

canvas.addEventListener("click", (evt) => {
  const [mx, my] = eventPoint(evt);
  const hit = binAt(mx, my);
  if (hit && hit.bin.rows.length > 0) openBucketModal(hit.channel, hit.bin);
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

buildPanelTabs();
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
