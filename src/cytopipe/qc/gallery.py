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
    together with a min/max number-input pair per channel (starting empty/unbounded). Thresholds
    are set by editing those inputs in the browser, out-of-range rows highlight live, and a
    button downloads the current exclusion list as a CSV, no server round trip involved.
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
  :root { color-scheme: light dark; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    margin: 1.5rem; line-height: 1.4;
  }
  h1 { font-size: 1.25rem; }
  p.hint { color: #666; max-width: 60em; }
  #controls {
    display: flex; flex-wrap: wrap; gap: 1rem; align-items: end;
    border: 1px solid #8884; border-radius: 8px; padding: 0.75rem 1rem; margin: 1rem 0;
  }
  .channel-range { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.85rem; }
  .channel-range .inputs { display: flex; gap: 0.35rem; align-items: center; }
  .channel-range input { width: 6rem; }
  #summary { font-weight: 600; }
  #download {
    margin-left: auto; padding: 0.5rem 1rem; border-radius: 6px; border: 1px solid #8884;
    cursor: pointer; font-weight: 600;
  }
  table { border-collapse: collapse; width: 100%; }
  th, td { padding: 0.4rem 0.6rem; border-bottom: 1px solid #8883; text-align: left; }
  th { position: sticky; top: 0; background: Canvas; cursor: pointer; user-select: none; }
  th.sorted::after { content: " \\25BE"; }
  img.thumb { width: 96px; height: 96px; object-fit: cover; border-radius: 4px; }
  td.out-of-range { background: color-mix(in srgb, orangered 25%, transparent); font-weight: 600; }
  tr.excluded-row { outline: 2px solid orangered; outline-offset: -2px; }
</style>
</head>
<body>
<h1>QC image review</h1>
<p class="hint">
  Set a min/max per channel below to flag images by eye. Out-of-range cells highlight live as
  you type, and rows currently flagged get an orange outline. Click a column header to sort. When
  satisfied, click &quot;Download exclusion list&quot; to save a CSV of the flagged
  Plate/Well/Site rows, then point <code>--qc_exclude_file</code> at that file.
</p>
<div id="controls"></div>
<p><span id="summary"></span> <button id="download">Download exclusion list</button></p>
<div style="overflow-x:auto">
<table>
  <thead><tr id="header-row"></tr></thead>
  <tbody id="rows"></tbody>
</table>
</div>
<script>
const CHANNELS = __CHANNELS_JSON__;
const ROWS = __ROWS_JSON__;

const controlsEl = document.getElementById("controls");
const headerRowEl = document.getElementById("header-row");
const rowsEl = document.getElementById("rows");
const summaryEl = document.getElementById("summary");

const COLUMNS = ["plate", "well", "site", "thumb", ...CHANNELS];
const LABELS = { plate: "Plate", well: "Well", site: "Site", thumb: "Image" };

let sortKey = null;
let sortAsc = true;

function currentBound(channel, side) {
  const el = document.getElementById(`range-${channel}-${side}`);
  const value = el.value.trim();
  return value === "" ? null : Number(value);
}

function isExcluded(row) {
  return CHANNELS.some((channel) => {
    const value = row.values[channel];
    const low = currentBound(channel, "min");
    const high = currentBound(channel, "max");
    return (low !== null && value < low) || (high !== null && value > high);
  });
}

function isOutOfRange(channel, value) {
  const low = currentBound(channel, "min");
  const high = currentBound(channel, "max");
  return (low !== null && value < low) || (high !== null && value > high);
}

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
    minInput.addEventListener("input", render);
    maxInput.addEventListener("input", render);
    inputs.append(minInput, document.createTextNode(" \\u2013 "), maxInput);
    wrap.append(label, inputs);
    controlsEl.append(wrap);
  }
}

function buildHeader() {
  for (const column of COLUMNS) {
    const th = document.createElement("th");
    th.textContent = LABELS[column] || column;
    th.dataset.column = column;
    if (column !== "thumb") {
      th.addEventListener("click", () => {
        sortAsc = sortKey === column ? !sortAsc : true;
        sortKey = column;
        render();
      });
    }
    headerRowEl.append(th);
  }
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

function render() {
  for (const th of headerRowEl.children) {
    th.classList.toggle("sorted", th.dataset.column === sortKey);
  }

  rowsEl.textContent = "";
  let flagged = 0;
  for (const row of sortedRows()) {
    const tr = document.createElement("tr");
    if (isExcluded(row)) {
      tr.className = "excluded-row";
      flagged += 1;
    }
    for (const column of COLUMNS) {
      const td = document.createElement("td");
      if (column === "thumb") {
        if (row.thumb) {
          const img = document.createElement("img");
          img.className = "thumb";
          img.src = row.thumb;
          img.alt = `${row.plate} ${row.well} site ${row.site}`;
          td.append(img);
        }
      } else if (column in row.values) {
        const value = row.values[column];
        td.textContent = value;
        if (isOutOfRange(column, value)) td.classList.add("out-of-range");
      } else {
        td.textContent = row[column];
      }
      tr.append(td);
    }
    rowsEl.append(tr);
  }
  summaryEl.textContent = `${flagged} of ${ROWS.length} images currently flagged`;
}

function csvEscape(value) {
  const text = String(value);
  return /[",\\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function download() {
  const excluded = ROWS.filter(isExcluded);
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

document.getElementById("download").addEventListener("click", download);
buildControls();
buildHeader();
render();
</script>
</body>
</html>
"""
