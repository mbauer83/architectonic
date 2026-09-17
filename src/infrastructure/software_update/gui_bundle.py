"""The served GUI: install a release's bundle beside the old one and swap, or build it locally.

`tools/gui/dist` is what `arch-backend` serves. A release bundle is a tarball of that directory; it
is unpacked next to it and swapped in with two renames, and the previous directory is kept as
`dist.previous` until the update is verified, so a rollback is the reverse rename. A build is the
same `npm ci && npm run build` the installation guide has always given.
"""

from __future__ import annotations

import io
import shutil
import tarfile
from pathlib import Path

from src.infrastructure.software_update._commands import CommandFailed, run_checked

GUI_DIR = Path("tools") / "gui"
DIST = "dist"
PREVIOUS = "dist.previous"
INCOMING = "dist.incoming"

_BUILD_TIMEOUT_SECONDS = 1800


class GuiBundleError(RuntimeError):
    pass


def install_bundle(root: Path, data: bytes) -> None:
    """Unpack a verified bundle and make it the served `dist`, keeping the previous one beside it."""
    gui = root / GUI_DIR
    incoming = gui / INCOMING
    shutil.rmtree(incoming, ignore_errors=True)
    incoming.mkdir(parents=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            archive.extractall(incoming, filter="data")
    except (tarfile.TarError, OSError, ValueError) as exc:
        shutil.rmtree(incoming, ignore_errors=True)
        raise GuiBundleError(f"the GUI bundle could not be unpacked: {exc}") from exc
    unpacked = incoming / DIST
    if not (unpacked / "index.html").is_file():
        shutil.rmtree(incoming, ignore_errors=True)
        raise GuiBundleError("the GUI bundle does not contain dist/index.html")
    _swap_in(gui, unpacked)
    shutil.rmtree(incoming, ignore_errors=True)


def build_locally(root: Path, *, npm: str = "npm") -> None:
    """`npm ci && npm run build` in `tools/gui`; the previous `dist` is kept for a rollback."""
    gui = root / GUI_DIR
    for command in ([npm, "ci", "--no-audit", "--no-fund"], [npm, "run", "build"]):
        try:
            run_checked(command, cwd=gui, timeout=_BUILD_TIMEOUT_SECONDS, doing=" ".join(command))
        except CommandFailed as exc:
            raise GuiBundleError(str(exc)) from exc


def keep_previous(root: Path) -> None:
    """Set the current `dist` aside as `dist.previous` before a build replaces it in place."""
    gui = root / GUI_DIR
    if (gui / DIST).is_dir():
        shutil.rmtree(gui / PREVIOUS, ignore_errors=True)
        shutil.copytree(gui / DIST, gui / PREVIOUS)


def restore_previous(root: Path) -> None:
    """Make `dist.previous` the served `dist` again; a no-op when there is none."""
    gui = root / GUI_DIR
    if not (gui / PREVIOUS).is_dir():
        return
    shutil.rmtree(gui / DIST, ignore_errors=True)
    (gui / PREVIOUS).rename(gui / DIST)


def discard_previous(root: Path) -> None:
    shutil.rmtree(root / GUI_DIR / PREVIOUS, ignore_errors=True)


def _swap_in(gui: Path, unpacked: Path) -> None:
    shutil.rmtree(gui / PREVIOUS, ignore_errors=True)
    if (gui / DIST).is_dir():
        (gui / DIST).rename(gui / PREVIOUS)
    unpacked.rename(gui / DIST)
