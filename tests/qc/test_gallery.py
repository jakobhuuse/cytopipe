"""
Tests for cytopipe.qc.gallery.
Self-contained HTML review gallery generation.
"""

import base64
import json
import re

from cytopipe.qc.gallery import build_gallery
from cytopipe.qc.scan import scan_qc_metrics


def _row(well, site, dna=-2.0, rna=-1.0, count=120, focus_dna=1.2, focus_rna=1.1, pct_dna=0.01, pct_rna=0.02):
    return {
        "Metadata_Plate": "26159",
        "Metadata_Well": well,
        "Metadata_Site": site,
        "Count_Nuclei": count,
        "ImageQuality_PowerLogLogSlope_OrigDNA": dna,
        "ImageQuality_PowerLogLogSlope_OrigRNA": rna,
        "ImageQuality_FocusScore_OrigDNA": focus_dna,
        "ImageQuality_FocusScore_OrigRNA": focus_rna,
        "ImageQuality_PercentMaximal_OrigDNA": pct_dna,
        "ImageQuality_PercentMaximal_OrigRNA": pct_rna,
    }


def _extract(html, name):
    match = re.search(rf"const {name} = (.*?);\n", html)
    assert match, f"could not find {name} in generated HTML"
    return json.loads(match.group(1))


def _panel(panels, key):
    return next(panel for panel in panels if panel["key"] == key)


def test_build_gallery_embeds_rows_and_panels(tmp_path, make_qc_dir):
    make_qc_dir(tmp_path, _row("A02", 1, dna=-2.0, rna=-1.0))
    make_qc_dir(tmp_path, _row("B03", 1, dna=-4.5, rna=-1.2))
    metrics = scan_qc_metrics(tmp_path)

    out = build_gallery(metrics, tmp_path / "gallery.html")
    assert out.exists()
    html = out.read_text()

    panels = _extract(html, "PANELS")
    assert _panel(panels, "blur") == {
        "key": "blur",
        "label": "Blur score",
        "shortLabel": "Blur",
        "thresholdMode": "range",
        "channels": ["DNA", "RNA"],
        "domainFloor": None,
        "domainCeiling": None,
    }
    assert _panel(panels, "cellCount")["channels"] == ["Nuclei"]
    assert _panel(panels, "cellCount")["domainFloor"] == 0
    assert _panel(panels, "percentMaximal")["thresholdMode"] == "max"
    assert _panel(panels, "percentMaximal")["domainCeiling"] == 1
    assert _panel(panels, "focusScore")["thresholdMode"] == "range"
    assert _panel(panels, "focusScore")["domainFloor"] == 0

    rows = _extract(html, "ROWS")
    assert len(rows) == 2
    by_well = {row["well"]: row for row in rows}
    assert by_well["B03"]["values"]["blur"]["DNA"] == -4.5
    assert by_well["A02"]["site"] == 1
    assert by_well["A02"]["values"]["cellCount"]["Nuclei"] == 120
    assert by_well["A02"]["values"]["percentMaximal"]["DNA"] == 0.01
    assert by_well["A02"]["values"]["focusScore"]["DNA"] == 1.2


def _thumb_src(html, key):
    match = re.search(rf'<img data-key="{re.escape(key)}" src="([^"]*)">', html)
    return match.group(1) if match else None


def test_build_gallery_embeds_thumbnail_as_hidden_img(tmp_path, make_qc_dir):
    make_qc_dir(tmp_path, _row("A02", 1))
    metrics = scan_qc_metrics(tmp_path)
    overlay_bytes = metrics["overlay_path"].iloc[0].read_bytes()

    out = build_gallery(metrics, tmp_path / "gallery.html")
    html = out.read_text()
    rows = _extract(html, "ROWS")
    assert rows[0]["hasThumb"] is True
    assert "thumb" not in rows[0]

    prefix = "data:image/png;base64,"
    src = _thumb_src(html, "26159|A02|1")
    assert src is not None and src.startswith(prefix)
    decoded = base64.b64decode(src[len(prefix) :])
    assert decoded == overlay_bytes


def test_build_gallery_missing_overlay_has_no_thumb(tmp_path, make_qc_dir):
    make_qc_dir(tmp_path, _row("A02", 1))
    (tmp_path / "chunk1" / "Overlays" / "26159_A02_1_overlay.png").unlink()
    metrics = scan_qc_metrics(tmp_path)

    out = build_gallery(metrics, tmp_path / "gallery.html")
    html = out.read_text()
    rows = _extract(html, "ROWS")
    assert rows[0]["hasThumb"] is False
    assert _thumb_src(html, "26159|A02|1") is None


def test_build_gallery_creates_parent_dirs(tmp_path, make_qc_dir):
    make_qc_dir(tmp_path, _row("A02", 1))
    metrics = scan_qc_metrics(tmp_path)

    out = build_gallery(metrics, tmp_path / "nested" / "dir" / "gallery.html")
    assert out.exists()
