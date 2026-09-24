"""An icon that arrived through git is held to what the upload path would have produced."""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from src.application.verification._verifier_icon import verify_icon
from src.domain.icons.icon_file import format_icon_file
from src.domain.icons.render_form import render_digest
from src.infrastructure.icons.raster_codec import StoredPngInspector
from src.infrastructure.mcp.artifact_mcp.verify_tools import artifact_verify
from tests.support.icon_files import icon_file, png_of, write_icon


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    return root


def _codes(path: Path) -> list[str]:
    return [issue.code for issue in verify_icon(path, inspector=StoredPngInspector()).issues]


def test_an_icon_the_upload_path_would_make_is_clean(repo: Path) -> None:
    assert _codes(write_icon(repo)) == []


def test_a_file_that_is_not_an_icon_is_e360(repo: Path) -> None:
    path = write_icon(repo)
    path.write_text(path.read_text().replace("```png-base64", "```png"), encoding="utf-8")

    assert _codes(path) == ["E360"]


def test_a_file_not_named_after_its_id_is_e361(repo: Path) -> None:
    path = write_icon(repo)
    moved = path.rename(path.with_name("ICO@1790000000.other1.x.md"))

    assert _codes(moved) == ["E361"]


def test_an_id_of_another_kind_is_e361(repo: Path) -> None:
    icon = icon_file()
    wrong = replace(icon, metadata=replace(icon.metadata, artifact_id="APP@1790000000.aks001.x"))

    assert _codes(write_icon(repo, wrong)) == ["E361"]


def test_a_picture_swapped_after_the_digest_was_taken_is_e362(repo: Path) -> None:
    path = write_icon(repo)
    other = icon_file(png=png_of((255, 0, 0, 255)))
    text = path.read_text()
    block = re.compile(r"```png-base64\n.*?\n```", re.DOTALL)
    path.write_text(block.sub(block.search(format_icon_file(other)).group(0), text), encoding="utf-8")

    assert _codes(path) == ["E362"]


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.mark.parametrize(
    "picture",
    [_jpeg(), png_of(size=(300, 20)), b"\x89PNG\r\n\x1a\nnot really"],
    ids=["not-a-png", "beyond-the-stored-edge", "truncated"],
)
def test_a_picture_the_upload_path_could_not_have_made_is_e363(repo: Path, picture: bytes) -> None:
    icon = icon_file(png=png_of())
    icon = replace(icon, png=picture, metadata=replace(icon.metadata, render_digest=render_digest(picture)))

    assert _codes(write_icon(repo, icon)) == ["E363"]


def test_a_declared_size_the_picture_does_not_have_is_e363(repo: Path) -> None:
    icon = icon_file()
    icon = replace(icon, metadata=replace(icon.metadata, width=99))

    assert _codes(write_icon(repo, icon)) == ["E363"]


def test_without_an_inspector_only_the_decode_is_skipped(repo: Path) -> None:
    icon = icon_file()
    swapped = replace(icon, png=_jpeg())
    path = write_icon(repo, swapped)

    assert [i.code for i in verify_icon(path, inspector=None).issues] == ["E362"]


def test_a_repository_pass_verifies_its_icons(repo: Path) -> None:
    write_icon(repo, replace(icon_file(), png=_jpeg()))

    result = asyncio.run(artifact_verify(repo_root=str(repo), repo_scope="engagement", confirm_full_pass=True,
                                         return_mode="full"))

    assert result["counts"]["files_by_type"].get("icon") == 1
    assert result["counts"]["errors"] >= 1


def test_verifying_one_icon_by_path_infers_its_kind(repo: Path) -> None:
    path = write_icon(repo)

    result = asyncio.run(artifact_verify(str(path), repo_root=str(repo), repo_scope="engagement"))

    assert result["file_type"] == "icon" and result["valid"] is True

