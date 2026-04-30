"""Thin CLI dispatcher for nanorunner.

Defines the Typer application, shared enums, and the app callback.
Subcommands are registered by importing cli_replay, cli_generate, and
cli_utils at the bottom of this module, which triggers their
``@app.command()`` decorators.

Validation lives in the config dataclasses, not here.
"""

import logging
import sys
from enum import Enum

import typer

from nanopore_simulator import __version__


# -------------------------------------------------------------------
# Enums
# -------------------------------------------------------------------


class TimingModelChoice(str, Enum):
    uniform = "uniform"
    random = "random"
    poisson = "poisson"
    adaptive = "adaptive"


class OperationChoice(str, Enum):
    copy = "copy"
    link = "link"


class MonitorLevel(str, Enum):
    default = "default"
    enhanced = "enhanced"
    none = "none"


class LogLevel(str, Enum):
    debug = "DEBUG"
    info = "INFO"
    warning = "WARNING"
    error = "ERROR"


class OutputFormat(str, Enum):
    fastq = "fastq"
    fastq_gz = "fastq.gz"


class GeneratorBackend(str, Enum):
    auto = "auto"
    builtin = "builtin"
    badread = "badread"
    nanosim = "nanosim"


class ForceStructure(str, Enum):
    singleplex = "singleplex"
    multiplex = "multiplex"


# -------------------------------------------------------------------
# Typer app
# -------------------------------------------------------------------

app = typer.Typer(
    name="nanorunner",
    help="Nanopore sequencing run simulator for testing bioinformatics pipelines.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
    pretty_exceptions_show_locals=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"nanorunner {__version__}")
        raise typer.Exit()


@app.callback()
def _app_callback(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.warning,
        "--log-level",
        help="Set logging verbosity.",
    ),
) -> None:
    """Nanopore sequencing run simulator for testing bioinformatics pipelines."""
    logging.basicConfig(
        level=getattr(logging, log_level.value),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------


def main() -> int:
    """Entry point for console_scripts."""
    try:
        app()
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0


if __name__ == "__main__":
    sys.exit(main())


# -------------------------------------------------------------------
# Import submodules to register their commands on `app`.
# These imports must come after `app` is defined.
# -------------------------------------------------------------------

from nanopore_simulator import cli_replay, cli_generate, cli_utils  # noqa: F401,E402
