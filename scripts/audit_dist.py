"""Fail the release if the built artifacts are incomplete or leak local state."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

DIST = Path("dist")
PACKAGE = "spookcli"
ASSETS = [
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
FORBIDDEN_PARTS = {".kiro", ".github", "docs", "tests", "opencode.json", "demonstration.md"}
FORBIDDEN_BYTES = [b"AQ.Ab8RN6"]


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_names(prefix: str, names: list[str]) -> None:
    for name in names:
        parts = Path(name).parts
        if any(part in FORBIDDEN_PARTS for part in parts):
            fail(f"{prefix} contains forbidden path: {name}")
        if name.endswith((".pyc", ".pyo")):
            fail(f"{prefix} contains compiled bytecode: {name}")


def check_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        check_names(path.name, names)

        expected = [f"{PACKAGE}/assets/{asset}" for asset in ASSETS]
        missing = [asset for asset in expected if asset not in names]
        if missing:
            fail(f"{path.name} missing assets: {', '.join(missing)}")

        if not any(name.endswith("dist-info/METADATA") for name in names):
            fail(f"{path.name} has no METADATA")
        if not any("dist-info/licenses/LICENSE" in name for name in names):
            fail(f"{path.name} has no bundled LICENSE")

        for name in names:
            data = archive.read(name)
            for marker in FORBIDDEN_BYTES:
                if marker in data:
                    fail(f"{path.name}:{name} contains {marker!r}")


def check_sdist(path: Path) -> None:
    with tarfile.open(path) as archive:
        names = archive.getnames()
        check_names(path.name, names)

        expected = [name for name in names if name.endswith(f"/{PACKAGE}/__init__.py")]
        if not expected:
            fail(f"{path.name} missing {PACKAGE}/__init__.py")
        if not any(name.endswith("/pyproject.toml") for name in names):
            fail(f"{path.name} missing pyproject.toml")

        for member in archive.getmembers():
            if not member.isfile():
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            data = handle.read()
            for marker in FORBIDDEN_BYTES:
                if marker in data:
                    fail(f"{path.name}:{member.name} contains {marker!r}")


def main() -> None:
    wheels = sorted(DIST.glob("*.whl"))
    sdists = sorted(DIST.glob("*.tar.gz"))

    if len(wheels) != 1:
        fail(f"expected exactly one wheel in {DIST}, found {len(wheels)}")
    if len(sdists) != 1:
        fail(f"expected exactly one sdist in {DIST}, found {len(sdists)}")

    check_wheel(wheels[0])
    check_sdist(sdists[0])
    print(f"OK: audited {wheels[0].name} and {sdists[0].name}")


if __name__ == "__main__":
    main()
