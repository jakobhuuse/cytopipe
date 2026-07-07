"""
Composed-CLI tests.
Commands load, expose help, and wire through to their module logic.
"""

import re

import pandas as pd
from typer.testing import CliRunner

from cytopipe.cli import app

runner = CliRunner()


def test_root_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("convert", "bridge", "loaddata", "report"):
        assert command in result.output


def test_convert_help_lists_subcommands():
    result = runner.invoke(app, ["convert", "--help"])
    assert result.exit_code == 0
    for sub in ("cellprofiler", "deepprofiler", "concat"):
        assert sub in result.output


def test_each_command_exposes_help():
    for args in (
        ["convert", "cellprofiler", "--help"],
        ["convert", "deepprofiler", "--help"],
        ["convert", "concat", "--help"],
        ["bridge", "--help"],
        ["loaddata", "--help"],
        ["report", "--help"],
    ):
        assert runner.invoke(app, args).exit_code == 0


def test_report_exposes_control_option():
    result = runner.invoke(app, ["report", "--help"])
    assert result.exit_code == 0
    # Strip ANSI / rich formatting that CI may add to help output
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    cleaned = ansi_escape.sub("", result.output)
    assert "--control" in cleaned


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
