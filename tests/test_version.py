"""Version and packaging metadata tests."""

from __future__ import annotations

import re
from pathlib import Path

import spookcli


def test_version_is_semverish() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[.-][0-9A-Za-z]+)*", spookcli.__version__)


def test_version_matches_pyproject_source() -> None:
    """pyproject uses hatch's path source; the file must stay authoritative."""
    init_file = Path(spookcli.__file__).with_name("__init__.py")
    assert f'__version__ = "{spookcli.__version__}"' in init_file.read_text(encoding="utf-8")


def test_pyproject_targets_this_package() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "spookcli"' in pyproject
    assert 'spook = "spookcli.cli:main"' in pyproject
    assert 'path = "spookcli/__init__.py"' in pyproject
