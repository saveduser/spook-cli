"""
Command runner — executes arbitrary shell commands and streams output in real-time.
"""

from __future__ import annotations

import subprocess
import sys
from typing import NamedTuple


class RunResult(NamedTuple):
    exit_code: int
    stdout: str
    stderr: str


def run_command(command: list[str]) -> RunResult:
    """
    Execute *command* via the system shell, streaming stdout and stderr to the
    terminal in real-time while also capturing both streams for inspection.

    shell=True is intentional: it lets users invoke shell built-ins (echo, dir,
    cd …) and shell features (pipes, globs) exactly as they would at the prompt.
    The command list is joined into a single string so the shell receives it
    correctly on both POSIX and Windows.

    Returns a RunResult with the final exit code and full captured output.
    """
    # Join args into a single shell string so built-ins (echo, dir, type…) work
    # on Windows and POSIX alike.
    shell_command = " ".join(command)

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    process = subprocess.Popen(
        shell_command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # line-buffered
    )

    # Stream stdout line by line as it arrives
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        stdout_lines.append(line)

    # Drain stderr after stdout closes (process has finished by this point)
    assert process.stderr is not None
    for line in process.stderr:
        sys.stderr.write(line)
        sys.stderr.flush()
        stderr_lines.append(line)

    process.wait()

    return RunResult(
        exit_code=process.returncode,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )
