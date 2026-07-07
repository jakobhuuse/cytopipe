"""cytopipe command-line interface. Composes each package's Typer app and commands."""

import typer

from cytopipe.bridge.cli import bridge_command
from cytopipe.convert.cli import app as convert_app
from cytopipe.loaddata.cli import loaddata_command
from cytopipe.report.cli import report_command

app = typer.Typer(
    name="cytopipe",
    help="CytoTable-based glue layer for a cell-painting feature-extraction pipeline.",
    no_args_is_help=True,
    add_completion=False,
)

# Groups are mounted with add_typer; single commands are registered directly.
app.add_typer(convert_app, name="convert")
app.command("bridge")(bridge_command)
app.command("loaddata")(loaddata_command)
app.command("report")(report_command)
