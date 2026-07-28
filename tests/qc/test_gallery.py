"""
Tests for cytopipe.qc.gallery.
Self-contained HTML review gallery generation.
"""

import base64
import json
import re

from cytopipe.qc.gallery import build_gallery
from cytopipe.qc.scan import scan_qc_metrics


def _row(well, site, dna=-2.0, rna=-1.0):
    return {
        "Metadata_Plate": "26159",
        "Metadata_Well": well,
        "Metadata_Site": site,
        "ImageQuality_PowerLogLogSlope_OrigDNA": dna,
        "ImageQuality_PowerLogLogSlope_OrigRNA": rna,
    }


def _extract(html, name):
    match = re.search(rf"const {name} = (.*?);\n", html)
    assert match, f"could not find {name} in generated HTML"
    return json.loads(match.group(1))


def test_build_gallery_embeds_rows_and_channels(tmp_path, make_qc_dir):
    make_qc_dir(tmp_path, _row("A02", 1, dna=-2.0, rna=-1.0))
    make_qc_dir(tmp_path, _row("B03", 1, dna=-4.5, rna=-1.2))
    metrics = scan_qc_metrics(tmp_path)

    out = build_gallery(metrics, tmp_path / "gallery.html")
    assert out.exists()
    html = out.read_text()

    channels = _extract(html, "CHANNELS")
    assert channels == ["DNA", "RNA"]

    rows = _extract(html, "ROWS")
    assert len(rows) == 2
    by_well = {row["well"]: row for row in rows}
    assert by_well["B03"]["values"]["DNA"] == -4.5
    assert by_well["A02"]["site"] == 1


def test_build_gallery_embeds_thumbnail_as_data_uri(tmp_path, make_qc_dir):
    make_qc_dir(tmp_path, _row("A02", 1))
    metrics = scan_qc_metrics(tmp_path)
    overlay_bytes = metrics["overlay_path"].iloc[0].read_bytes()

    out = build_gallery(metrics, tmp_path / "gallery.html")
    rows = _extract(out.read_text(), "ROWS")

    prefix = "data:image/png;base64,"
    assert rows[0]["thumb"].startswith(prefix)
    decoded = base64.b64decode(rows[0]["thumb"][len(prefix) :])
    assert decoded == overlay_bytes


def test_build_gallery_missing_overlay_is_empty_thumb(tmp_path, make_qc_dir):
    make_qc_dir(tmp_path, _row("A02", 1))
    (tmp_path / "chunk1" / "Overlays" / "26159_A02_1_overlay.png").unlink()
    metrics = scan_qc_metrics(tmp_path)

    out = build_gallery(metrics, tmp_path / "gallery.html")
    rows = _extract(out.read_text(), "ROWS")
    assert rows[0]["thumb"] == ""


def test_build_gallery_creates_parent_dirs(tmp_path, make_qc_dir):
    make_qc_dir(tmp_path, _row("A02", 1))
    metrics = scan_qc_metrics(tmp_path)

    out = build_gallery(metrics, tmp_path / "nested" / "dir" / "gallery.html")
    assert out.exists()
