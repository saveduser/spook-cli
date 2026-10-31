"""
SpookCLI entry point.

Usage:
    spook run <command> [args...]

Examples:
    spook run ls -la
    spook run python myscript.py
    spook run git push origin main
"""

from __future__ import annotations

import os
import sys

# Force UTF-8 on Windows so emoji in click.style() don't crash on cp1252 terminals.
# Must happen before any click/rich import.
if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

import click

from spookcli.ghost import trigger_ghost_event
from spookcli.runner import run_command

# ANSI colour helpers via click so Windows is handled automatically.
SUCCESS_STYLE = {"fg": "green", "bold": True}
ERROR_STYLE = {"fg": "red", "bold": True}
BANNER_STYLE = {"fg": "yellow", "bold": True}


def _banner() -> None:
    click.echo(click.style("[SpookCLI] Beware of failing commands...", **BANNER_STYLE))


@click.group()
def main() -> None:
    """SpookCLI 👻 — a Halloween-themed command wrapper."""


@main.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
@click.argument("command", nargs=-1, required=True)
def run(command: tuple[str, ...]) -> None:
    """
    Run COMMAND, streaming its output. Summons a ghost on failure.

    \b
    Examples:
      spook run echo hello
      spook run python -c "import sys; sys.exit(1)"
    """
    _banner()
    click.echo(
        click.style(f"▶  Running: {' '.join(command)}", fg="cyan"),
        err=False,
    )
    click.echo("")

    result = run_command(list(command))

    click.echo("")  # blank line separator before verdict

    if result.exit_code == 0:
        click.echo(
            click.style(
                "SUCCESS: Command succeeded (exit 0).",
                **SUCCESS_STYLE,
            )
        )
        sys.exit(0)
    else:
        # Print captured stderr in red (it was already streamed live;
        # this block re-surfaces it as a highlighted summary).
        if result.stderr.strip():
            click.echo(
                click.style("-- stderr ------------------------------------------", fg="red"),
                err=True,
            )
            click.echo(click.style(result.stderr.rstrip(), fg="red"), err=True)
            click.echo(
                click.style("----------------------------------------------------", fg="red"),
                err=True,
            )

        click.echo(
            click.style(
                f"FAILED: Command exited with code {result.exit_code}.",
                **ERROR_STYLE,
            ),
            err=True,
        )

        trigger_ghost_event()
        sys.exit(result.exit_code)
