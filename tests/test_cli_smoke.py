"""Smoke tests: the CLI loads and its commands expose help without error."""

from typer.testing import CliRunner

from cytopipe.cli import app

runner = CliRunner()


def test_root_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "cellprofiler-parquet" in result.output
    assert "deepprofiler-parquet" in result.output
    assert "cellprofiler-deepprofiler" in result.output


def test_cellprofiler_parquet_help():
    result = runner.invoke(app, ["cellprofiler-parquet", "--help"])
    assert result.exit_code == 0


def test_deepprofiler_parquet_help():
    result = runner.invoke(app, ["deepprofiler-parquet", "--help"])
    assert result.exit_code == 0


def test_bridge_help():
    result = runner.invoke(app, ["cellprofiler-deepprofiler", "--help"])
    assert result.exit_code == 0
