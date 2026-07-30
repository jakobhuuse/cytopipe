"""
Composed-CLI tests.
Commands load, expose help, and wire through to their module logic.
"""

import sqlite3
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from cytopipe.cli import app
from cytopipe.convert import parquet
from cytopipe.convert.cli import app as convert_app
from cytopipe.report import cli as report_cli
from cytopipe.report.figures import FigureSkipped

runner = CliRunner()


def test_root_app_registers_all_commands():
    commands = {command.name for command in app.registered_commands}
    groups = {group.name for group in app.registered_groups}
    assert {"aggregate", "bridge", "loaddata", "loaddata-filter", "qc", "report"} <= commands
    assert "convert" in groups


def test_convert_app_registers_subcommands():
    subcommands = {command.name for command in convert_app.registered_commands}
    assert {"cellprofiler", "deepprofiler", "concat"} <= subcommands


def test_each_command_exposes_help():
    for args in (
        ["convert", "cellprofiler", "--help"],
        ["convert", "deepprofiler", "--help"],
        ["convert", "concat", "--help"],
        ["aggregate", "--help"],
        ["bridge", "--help"],
        ["loaddata", "--help"],
        ["loaddata-filter", "--help"],
        ["qc", "--help"],
        ["report", "--help"],
    ):
        assert runner.invoke(app, args).exit_code == 0


# --- functional invocations -------------------------------------------------------------------


def test_bridge_command_runs_end_to_end(measurement_dir, platemap_default, tmp_path):
    out = tmp_path / "out"
    result = runner.invoke(app, ["bridge", str(measurement_dir), str(out), str(platemap_default)])
    assert result.exit_code == 0, result.output
    assert "26159" in result.output
    assert (out / "metadata" / "index.csv").exists()


def test_loaddata_command_runs_end_to_end(make_plate, tmp_path):
    plate_dir = make_plate(tmp_path / "26159")
    out = tmp_path / "ld.csv"
    result = runner.invoke(app, ["loaddata", str(plate_dir), str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()


def test_loaddata_filter_command_runs_end_to_end(make_plate, tmp_path):
    plate_dir = make_plate(tmp_path / "26159")
    load_data_csv = tmp_path / "ld.csv"
    runner.invoke(app, ["loaddata", str(plate_dir), str(load_data_csv)])

    exclude_csv = tmp_path / "excluded.csv"
    pd.DataFrame(
        {"Metadata_Plate": ["26159"], "Metadata_Well": ["A02"], "Metadata_Site": [1]}
    ).to_csv(exclude_csv, index=False)

    out = tmp_path / "filtered.csv"
    result = runner.invoke(
        app, ["loaddata-filter", str(load_data_csv), str(exclude_csv), str(out)]
    )
    assert result.exit_code == 0, result.output
    assert len(pd.read_csv(out)) == 1  # one of the two sites in make_plate's default dropped


def test_qc_review_command_runs_end_to_end(tmp_path, make_qc_dir):
    row = {
        "Metadata_Plate": "26159",
        "Metadata_Well": "A02",
        "Metadata_Site": 1,
        "Count_Nuclei": 120,
        "ImageQuality_PowerLogLogSlope_OrigDNA": -2.0,
        "ImageQuality_FocusScore_OrigDNA": 1.2,
        "ImageQuality_PercentMaximal_OrigDNA": 0.01,
    }
    qc_dir = make_qc_dir(tmp_path / "qc", row)
    out_dir = tmp_path / "review"

    result = runner.invoke(app, ["qc", str(qc_dir), "--out-dir", str(out_dir)])

    assert result.exit_code == 0, result.output
    assert (out_dir / "gallery.html").exists()


def test_aggregate_command_runs_end_to_end(tmp_path):
    src = tmp_path / "sc.parquet"
    pd.DataFrame(
        {
            "Metadata_Plate": ["p1", "p1"],
            "Metadata_Well": ["A01", "A01"],
            "Cells_Area": [1.0, 3.0],
        }
    ).to_parquet(src)
    dest = tmp_path / "agg.parquet"

    ok = runner.invoke(
        app,
        [
        "aggregate", str(src), str(dest),
        "--strata", "Metadata_Plate,Metadata_Well",
        "--threads",
        "1"
        ],
    )
    assert ok.exit_code == 0, ok.output
    assert pd.read_parquet(dest)["Cells_Area"].iloc[0] == 2.0

    # An unknown feature hits the shared error path and exits non-zero.
    fail = runner.invoke(
        app,
        ["aggregate", str(src), str(tmp_path / "x.parquet"),
         "--strata", "Metadata_Well", "--features", "Nope"],
    )
    assert fail.exit_code == 1
    assert "failed" in fail.output


def _make_cp_sqlite(path: Path, *, objects: int) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE Per_Image (ImageNumber INTEGER)")
    con.execute("INSERT INTO Per_Image VALUES (1)")
    for name in ("Cells", "Nuclei", "Cytoplasm"):
        con.execute(f"CREATE TABLE Per_{name} (ImageNumber INTEGER, ObjectNumber INTEGER)")
        for i in range(1, objects + 1):
            con.execute(f"INSERT INTO Per_{name} VALUES (1, ?)", (i,))
    con.commit()
    con.close()


def test_convert_cellprofiler_command_writes_skipped_manifest(tmp_path, monkeypatch):
    measurement = tmp_path / "measurement"
    measurement.mkdir()
    _make_cp_sqlite(measurement / "plate.1.sqlite", objects=3)  # populated
    _make_cp_sqlite(measurement / "plate.2.sqlite", objects=0)  # empty, must be skipped
    dest = tmp_path / "out.parquet"

    def fake_convert(source_path, dest_path, preset, *, threads=2, **kwargs):
        Path(dest_path).write_bytes(b"")

    monkeypatch.setattr(parquet, "convert_to_parquet", fake_convert)

    result = runner.invoke(app, ["convert", "cellprofiler", str(measurement), str(dest)])

    assert result.exit_code == 0, result.output
    manifest = tmp_path / "out.parquet.skipped.txt"
    assert manifest.exists()
    assert "plate.2.sqlite" in manifest.read_text()
    assert "plate.1.sqlite" not in manifest.read_text()


def _make_report_results_dir(tmp_path):
    engine_dir = tmp_path / "results" / "deepprofiler"
    normalized = engine_dir / "normalized"
    normalized.mkdir(parents=True)
    pd.DataFrame(
        {"Metadata_Plate": ["p1"], "Metadata_Well": ["A01"], "efficientnet_1": [1.0]}
    ).to_parquet(normalized / "p1.parquet")
    return engine_dir


def test_report_command_exits_zero_when_figures_only_skip(tmp_path, monkeypatch):
    results_dir = _make_report_results_dir(tmp_path)

    def skip(*args, **kwargs):
        raise FigureSkipped("not enough data")

    monkeypatch.setattr(report_cli, "plate_heatmaps", skip)
    monkeypatch.setattr(report_cli, "embedding_umap", skip)
    monkeypatch.setattr(report_cli, "replicate_reproducibility", skip)
    monkeypatch.setattr(report_cli, "similarity_clustermap", skip)

    result = runner.invoke(app, ["report", str(results_dir), "--out", str(tmp_path / "out")])

    assert result.exit_code == 0, result.output
    assert "skipped" in result.output


def test_report_command_exits_nonzero_on_genuine_figure_error(tmp_path, monkeypatch):
    results_dir = _make_report_results_dir(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected bug")

    def skip(*args, **kwargs):
        raise FigureSkipped("not enough data")

    monkeypatch.setattr(report_cli, "plate_heatmaps", boom)
    monkeypatch.setattr(report_cli, "embedding_umap", skip)
    monkeypatch.setattr(report_cli, "replicate_reproducibility", skip)
    monkeypatch.setattr(report_cli, "similarity_clustermap", skip)

    result = runner.invoke(app, ["report", str(results_dir), "--out", str(tmp_path / "out")])

    # A genuine bug must not be reported as overall success.
    assert result.exit_code == 1
    assert "1 plate heatmaps: failed" in result.output
    assert "RuntimeError: unexpected bug" in result.output


def test_convert_concat_command_runs_and_reports_failure(tmp_path):
    parts = tmp_path / "parts"
    parts.mkdir()
    pd.DataFrame({"id": [1]}).to_parquet(parts / "a.parquet")
    pd.DataFrame({"id": [2]}).to_parquet(parts / "b.parquet")
    dest = tmp_path / "out.parquet"

    ok = runner.invoke(app, ["convert", "concat", str(parts), str(dest), "--threads", "1"])
    assert ok.exit_code == 0, ok.output
    assert dest.exists()

    # Empty (but existing) dir has no parquets → the shared error path exits non-zero.
    empty = tmp_path / "empty"
    empty.mkdir()
    fail = runner.invoke(app, ["convert", "concat", str(empty), str(tmp_path / "x.parquet")])
    assert fail.exit_code == 1
    assert "failed" in fail.output
