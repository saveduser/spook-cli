# Changelog

All notable changes to SpookCLI are documented here. This project follows
[Semantic Versioning](https://semver.org/) and [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2026-11-08

First public release. 🎃

### Added

- `spook run <command>` — streams a command's output and summons a Kiro ghost
  overlay when it fails.
- `spook gtop` — a frameless, glassmorphic PyQt6 process monitor with live
  `psutil` telemetry, CPU/RAM soul gauges, a crypt for exorcised processes, and
  a flying-Kiro mascot.
- **Port Hauntings** — listening TCP ports are mapped to owning PIDs; holders
  of common dev ports get a badge and a one-click Exorcise button.
- **Curse / Uncurse** — `c` sends `SIGSTOP`/`SIGCONT`, pins cursed rows, and
  automatically resumes every cursed process on exit. PID `0`, `1`, and gtop
  itself are protected.
- **Trace Bloodline** — `Shift+T` renders the selected process's descendant
  tree and highlights the suspected leak with a `LEAK` tag.
- **Bloodline leak detection** — tracks RSS growth across snapshots and falls
  back to the largest resident process.
- `spook board` — a retro BBS scoreboard backed by `~/.spookcli_stats.json`.
- `spook install-hook` — idempotent PowerShell, Zsh, and Bash prompt hooks.
- `spook test-ghost` — developer shortcut for exercising the overlay.
- Bundled audio and mascot assets packaged inside the wheel.
- CI across Python 3.10–3.13 and Trusted Publishing workflows for TestPyPI
  and PyPI.

### Security

- Release artifacts are audited to ensure local configuration such as
  `opencode.json` and API keys are never included.

[0.1.0]: https://github.com/saveduser/spook-cli/releases/tag/v0.1.0
