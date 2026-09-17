"""A release bundle becomes the served `dist` by a swap that a rollback reverses."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from src.infrastructure.software_update.gui_bundle import (
    GuiBundleError,
    discard_previous,
    install_bundle,
    restore_previous,
)


def _bundle(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


@pytest.fixture()
def checkout(tmp_path: Path) -> Path:
    dist = tmp_path / "tools" / "gui" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("old")
    return tmp_path


def test_the_bundle_is_swapped_in_and_the_previous_dist_kept_until_discarded(checkout: Path) -> None:
    install_bundle(checkout, _bundle({"dist/index.html": "new", "dist/assets/app.js": "js"}))

    gui = checkout / "tools" / "gui"
    assert (gui / "dist" / "index.html").read_text() == "new"
    assert (gui / "dist" / "assets" / "app.js").read_text() == "js"
    assert (gui / "dist.previous" / "index.html").read_text() == "old"
    assert not (gui / "dist.incoming").exists()

    discard_previous(checkout)
    assert not (gui / "dist.previous").exists()


def test_restoring_puts_the_previous_dist_back(checkout: Path) -> None:
    install_bundle(checkout, _bundle({"dist/index.html": "new"}))

    restore_previous(checkout)

    gui = checkout / "tools" / "gui"
    assert (gui / "dist" / "index.html").read_text() == "old" and not (gui / "dist.previous").exists()
    restore_previous(checkout)  # idempotent: a second rollback attempt changes nothing
    assert (gui / "dist" / "index.html").read_text() == "old"


def test_a_bundle_without_the_served_page_is_refused_and_leaves_dist_alone(checkout: Path) -> None:
    with pytest.raises(GuiBundleError, match="index.html"):
        install_bundle(checkout, _bundle({"dist/readme.txt": "x"}))

    gui = checkout / "tools" / "gui"
    assert (gui / "dist" / "index.html").read_text() == "old" and not (gui / "dist.incoming").exists()


def test_a_bundle_that_escapes_its_directory_is_refused(checkout: Path) -> None:
    with pytest.raises(GuiBundleError):
        install_bundle(checkout, _bundle({"dist/index.html": "new", "../escape.txt": "x"}))

    assert not (checkout / "tools" / "escape.txt").exists()
