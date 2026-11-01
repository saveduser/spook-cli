"""
SpookCLI entry point.

Usage:
    spook run <command> [args...]
    spook trigger
    spook install-hook
    spook test-ghost

Examples:
    spook run ls -la
    spook run python myscript.py
    spook install-hook
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

import subprocess
from pathlib import Path

import click

from spookcli.ghost import trigger_ghost_event
from spookcli.runner import run_command

# ANSI colour helpers via click so Windows is handled automatically.
SUCCESS_STYLE = {"fg": "green", "bold": True}
ERROR_STYLE   = {"fg": "red",   "bold": True}
BANNER_STYLE  = {"fg": "yellow","bold": True}
INFO_STYLE    = {"fg": "cyan",  "bold": False}

# Unique marker embedded in the hook snippet so install-hook is idempotent.
_HOOK_MARKER = "# SpookCLI shell hook"


def _banner() -> None:
    click.echo(click.style("[SpookCLI] Beware of failing commands...", **BANNER_STYLE))


# ---------------------------------------------------------------------------
# Helpers shared by install-hook
# ---------------------------------------------------------------------------

def _spook_exe() -> str:
    """
    Return the absolute path to the spook executable that is currently
    running so the hook snippet points at the right binary regardless of PATH.
    """
    return str(Path(sys.executable).parent / ("spook.exe" if sys.platform == "win32" else "spook"))


def _is_hook_installed(profile_path: Path) -> bool:
    """Return True if the SpookCLI marker is already present in *profile_path*."""
    if not profile_path.exists():
        return False
    return _HOOK_MARKER in profile_path.read_text(encoding="utf-8", errors="replace")


def _append_hook(profile_path: Path, snippet: str) -> None:
    """Ensure the parent directory exists, then append *snippet* to *profile_path*."""
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    with profile_path.open("a", encoding="utf-8") as fh:
        fh.write(snippet)


# ---------------------------------------------------------------------------
# Shell snippet factories
# ---------------------------------------------------------------------------

def _powershell_snippet(spook_exe: str) -> str:
    r"""
    PowerShell prompt hook — compatible with Windows PowerShell 5.1+.

    Wraps the built-in `prompt` function. If the previous command's
    $LASTEXITCODE was non-zero, fires `spook trigger` as a detached
    background job so the prompt returns immediately.

    Uses Start-Process -WindowStyle Hidden so no console window flashes.
    """
    # PowerShell single-quoted strings treat backslash as literal — no escaping needed.
    exe_ps = spook_exe
    return f"""
{_HOOK_MARKER} -- do not edit this block manually
function prompt {{
    $code = $global:LASTEXITCODE
    if ($code -ne 0 -and $null -ne $code) {{
        Start-Process -FilePath '{exe_ps}' `
            -ArgumentList 'trigger' `
            -WindowStyle Hidden
    }}
    $global:LASTEXITCODE = $code
    "PS $($ExecutionContext.SessionState.Path.CurrentLocation)$('>' * ($NestedPromptLevel + 1)) "
}}
{_HOOK_MARKER} end
"""


def _zsh_snippet(spook_exe: str) -> str:
    """Zsh precmd hook appended to ~/.zshrc."""
    return f"""
{_HOOK_MARKER} — do not edit this block manually
_spookcli_precmd() {{
    local code=$?
    if [ "$code" -ne 0 ]; then
        '{spook_exe}' trigger &>/dev/null &
        disown
    fi
}}
precmd_functions+=(_spookcli_precmd)
{_HOOK_MARKER} end
"""


def _bash_snippet(spook_exe: str) -> str:
    """Bash PROMPT_COMMAND hook appended to ~/.bashrc."""
    return f"""
{_HOOK_MARKER} — do not edit this block manually
_spookcli_prompt_cmd() {{
    local code=$?
    if [ "$code" -ne 0 ]; then
        '{spook_exe}' trigger &>/dev/null &
        disown
    fi
}}
PROMPT_COMMAND="${{PROMPT_COMMAND:+${{PROMPT_COMMAND}}; }}_spookcli_prompt_cmd"
{_HOOK_MARKER} end
"""


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.group()
def main() -> None:
    """SpookCLI -- a Halloween-themed command wrapper."""


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
        click.style(f">>  Running: {' '.join(command)}", fg="cyan"),
        err=False,
    )
    click.echo("")

    result = run_command(list(command))

    click.echo("")  # blank line separator before verdict

    if result.exit_code == 0:
        click.echo(click.style("SUCCESS: Command succeeded (exit 0).", **SUCCESS_STYLE))
        sys.exit(0)
    else:
        if result.stderr.strip():
            click.echo(click.style("-- stderr ------------------------------------------", fg="red"), err=True)
            click.echo(click.style(result.stderr.rstrip(), fg="red"), err=True)
            click.echo(click.style("----------------------------------------------------", fg="red"), err=True)

        click.echo(
            click.style(f"FAILED: Command exited with code {result.exit_code}.", **ERROR_STYLE),
            err=True,
        )

        trigger_ghost_event(stderr_text=result.stderr)
        sys.exit(result.exit_code)


@main.command()
def trigger() -> None:
    """
    Silently launch the ghost overlay (used by shell background hooks).

    Intended to be called by the shell hook installed via `spook install-hook`.
    Produces no terminal output — all side-effects are visual/audio.
    """
    # Use sys.executable so the child always runs inside the same virtual-env
    # Python that is currently active — no dependence on PATH or a `spook`
    # script being discoverable as a bare filename.
    cmd = [sys.executable, "-m", "spookcli.cli", "_ghost-overlay"]

    kwargs: dict = {}
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP — fully orphaned on Windows
        DETACHED_PROCESS      = 0x00000008
        CREATE_NEW_PROC_GROUP = 0x00000200
        kwargs = {
            "creationflags": DETACHED_PROCESS | CREATE_NEW_PROC_GROUP,
            "close_fds": True,
        }
    else:
        kwargs = {"start_new_session": True}

    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )


@main.command(name="_ghost-overlay", hidden=True)
def _ghost_overlay_worker() -> None:
    """
    Internal: run the ghost overlay in-process.

    Called by `spook trigger` as a detached subprocess so it can run the
    PyQt6 event loop without blocking the user's shell prompt.
    """
    trigger_ghost_event(stderr_text="")


@main.command("install-hook")
@click.option(
    "--shell",
    type=click.Choice(["auto", "powershell", "zsh", "bash"], case_sensitive=False),
    default="auto",
    show_default=True,
    help="Target shell. 'auto' detects from OS and $SHELL.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print what would be written without touching any files.",
)
def install_hook(shell: str, dry_run: bool) -> None:
    """
    Install a shell hook that auto-triggers the ghost on any failed command.

    Appends a small hook snippet to your shell profile. The hook is
    idempotent — running install-hook twice will not duplicate the snippet.

    \b
    Profiles modified:
      PowerShell  $PROFILE  (~/.../Microsoft.PowerShell_profile.ps1)
      Zsh         ~/.zshrc
      Bash        ~/.bashrc

    Restart your terminal (or `source` the profile) to activate.
    """
    spook_exe = _spook_exe()

    # ── shell detection ──────────────────────────────────────────────────
    if shell == "auto":
        if sys.platform == "win32":
            shell = "powershell"
        else:
            login_shell = os.environ.get("SHELL", "")
            if "zsh" in login_shell:
                shell = "zsh"
            else:
                shell = "bash"

    # ── pick profile path + snippet ──────────────────────────────────────
    home = Path.home()

    if shell == "powershell":
        # Mirror exactly what PowerShell exposes as $PROFILE
        profile_path = (
            home / "Documents" / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"
        )
        snippet = _powershell_snippet(spook_exe)
        reload_hint = ". $PROFILE"
    elif shell == "zsh":
        profile_path = home / ".zshrc"
        snippet = _zsh_snippet(spook_exe)
        reload_hint = "source ~/.zshrc"
    else:  # bash
        profile_path = home / ".bashrc"
        snippet = _bash_snippet(spook_exe)
        reload_hint = "source ~/.bashrc"

    # ── idempotency check ────────────────────────────────────────────────
    if _is_hook_installed(profile_path):
        click.echo(
            click.style(
                f"[SpookCLI] Hook already installed in {profile_path}. Nothing to do.",
                fg="yellow",
            )
        )
        return

    # ── dry-run mode ─────────────────────────────────────────────────────
    if dry_run:
        click.echo(click.style(f"[SpookCLI] DRY RUN — would append to {profile_path}:", **BANNER_STYLE))
        click.echo(click.style(snippet, fg="white"))
        return

    # ── write ────────────────────────────────────────────────────────────
    try:
        _append_hook(profile_path, snippet)
    except OSError as exc:
        click.echo(
            click.style(f"[SpookCLI] ERROR: could not write to {profile_path}: {exc}", **ERROR_STYLE),
            err=True,
        )
        sys.exit(1)

    # ── success message ──────────────────────────────────────────────────
    click.echo(click.style(f"[SpookCLI] Hook installed successfully!", **SUCCESS_STYLE))
    click.echo(click.style(f"  Profile : {profile_path}", **INFO_STYLE))
    click.echo(click.style(f"  Shell   : {shell}", **INFO_STYLE))
    click.echo(click.style(f"  Spook   : {spook_exe}", **INFO_STYLE))
    click.echo("")
    click.echo(click.style("Next steps:", bold=True))
    click.echo(f"  1. Reload your shell config:  {reload_hint}")
    click.echo(f"  2. Run any failing command — the ghost will appear automatically.")
    click.echo(f"  3. To remove the hook, delete the lines between")
    click.echo(f"     '{_HOOK_MARKER}' and '{_HOOK_MARKER} end' in {profile_path}")


@main.command("board")
def board() -> None:
    """
    Open the Haunted BBS — a retro bulletin board showing your failure stats.

    Plays a dial-up connection sequence, then renders the board with:
    the Developer Cemetery (failure counts), Latest Haunt Logs, and
    a spooky Message of the Day. Press Q + Enter to disconnect.
    """
    from spookcli.board import run_board
    run_board()


@main.command("test-ghost")
def test_ghost() -> None:
    """
    Developer shortcut: trigger the full ghost event without running a command.

    Plays ghost_scream.wav, shows the AI diagnosis bubble and animated overlay,
    then exits cleanly. Useful for verifying assets during development.
    """
    fake_stderr = "ModuleNotFoundError: No module named 'cauldron'"
    click.echo(click.style("[SpookCLI] Triggering ghost event for testing...", fg="yellow", bold=True))
    click.echo(click.style(f"[SpookCLI] Fake stderr: {fake_stderr}", fg="yellow"))
    trigger_ghost_event(stderr_text=fake_stderr)
    click.echo(click.style("[SpookCLI] Ghost event completed.", fg="green", bold=True))



if __name__ == "__main__":
    main()
