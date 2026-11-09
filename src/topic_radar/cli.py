import asyncio
from pathlib import Path

import typer

from .pipeline import INTERRUPTED, run_watch

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main() -> None:
    """A local digest of what's new in the topics you follow."""


@app.command()
def run(
    watch: str = typer.Argument(..., help="The watch to run: the name of a file in watches/, without .yaml."),
    folder: Path = typer.Option(Path("."), help="The Topic Radar folder (holds watches/ and runs/)."),
    read_cap: int | None = typer.Option(None, min=0, help="Most articles to read in full this run."),
    model: str | None = typer.Option(None, help="The Ollama model to use instead of the default."),
) -> None:
    """Run one watch and write its report."""
    try:
        outcome = asyncio.run(run_watch(watch, folder, read_cap=read_cap, model=model))
    except KeyboardInterrupt:
        raise typer.Exit(INTERRUPTED) from None
    if outcome.code == 2:
        typer.echo(outcome.message, err=True)
    elif outcome.code == 0:
        typer.echo("The report is ready. To open it, double-click it in Finder or File Explorer, "
                   "or open it in any text editor:")
        typer.echo(str(outcome.report.resolve()))
    raise typer.Exit(outcome.code)
