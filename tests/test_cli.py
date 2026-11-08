"""CLI surface tests — no Qt, no ghost overlay, no real hover."""

from __future__ import annotations

from click.testing import CliRunner

import spookcli
from spookcli.cli import main


def test_help_lists_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "gtop", "board", "install-hook", "test-ghost"):
        assert command in result.output


def test_version_flag() -> None:
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert spookcli.__version__ in result.output


def test_successful_run_does_not_summon_ghost() -> None:
    result = CliRunner().invoke(main, ["run", "echo", "hello"])
    assert result.exit_code == 0
    assert "SUCCESS" in result.output


def test_install_hook_dry_run_writes_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    profile = tmp_path / ".bashrc"

    result = CliRunner().invoke(main, ["install-hook", "--shell", "bash", "--dry-run"])

    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    assert "SpookCLI shell hook" in result.output
    assert not profile.exists()


def test_install_hook_is_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    profile = tmp_path / ".bashrc"
    runner = CliRunner()

    first = runner.invoke(main, ["install-hook", "--shell", "bash"])
    second = runner.invoke(main, ["install-hook", "--shell", "bash"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "already installed" in second.output
    assert profile.read_text(encoding="utf-8").count("SpookCLI shell hook") == 2
