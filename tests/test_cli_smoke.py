"""Smoke tests: the CLI loads and its commands expose help without error."""

from typer.testing import CliRunner

from cytopipe.cli import app

runner = CliRunner()


def test_root_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "convert" in result.output
    assert "bridge" in result.output
    assert "loaddata" in result.output


def test_convert_help_lists_subcommands():
    result = runner.invoke(app, ["convert", "--help"])
    assert result.exit_code == 0
    assert "cellprofiler" in result.output
    assert "deepprofiler" in result.output
    assert "concat" in result.output


def test_convert_cellprofiler_help():
    result = runner.invoke(app, ["convert", "cellprofiler", "--help"])
    assert result.exit_code == 0


def test_convert_deepprofiler_help():
    result = runner.invoke(app, ["convert", "deepprofiler", "--help"])
    assert result.exit_code == 0


def test_convert_concat_help():
    result = runner.invoke(app, ["convert", "concat", "--help"])
    assert result.exit_code == 0


def test_bridge_help():
    result = runner.invoke(app, ["bridge", "--help"])
    assert result.exit_code == 0


def test_loaddata_help():
    result = runner.invoke(app, ["loaddata", "--help"])
    assert result.exit_code == 0
