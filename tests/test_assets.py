"""Every runtime asset must ship inside the package."""

from __future__ import annotations

from pathlib import Path

import pytest

ASSETS_DIR = Path(__file__).resolve().parents[1] / "spookcli" / "assets"

EXPECTED_ASSETS = [
    "Ghost_in_the_Cabinet.mp3",
    "Possessed_High_Score.mp3",
    "blinking_ghost.gif",
    "collected.wav",
    "exorcism1.wav",
    "exorcism2.wav",
    "ghost-kiro-blink.gif",
    "ghost_scream.wav",
    "pumpkin.png",
]


@pytest.mark.parametrize("name", EXPECTED_ASSETS)
def test_asset_exists_and_is_not_empty(name: str) -> None:
    path = ASSETS_DIR / name
    assert path.is_file(), f"missing packaged asset: {name}"
    assert path.stat().st_size > 0, f"empty packaged asset: {name}"


def test_no_stray_asset_count() -> None:
    shipped = sorted(p.name for p in ASSETS_DIR.iterdir() if p.is_file())
    assert shipped == sorted(EXPECTED_ASSETS)
