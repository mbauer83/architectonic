"""The weights are the one shipped artefact no lock file governs, so this module governs them.

A missing or tampered file must disable vector retrieval and say which file failed — never load
silently, and never take keyword search down with it. These tests state that over a tree the test
itself builds, so they hold whether or not a real 31 MB asset is installed on the machine running
them.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.infrastructure.bootstrap import embedding_model_asset as asset
from src.infrastructure.bootstrap.embedding_model_asset import (
    ENV_MODEL_DIRECTORY,
    MODEL_FILES,
    MODEL_REVISION,
    PinnedFile,
    file_url,
    installed_model_directory,
    integrity_failures,
    model_directory,
)


def _install(directory: Path, files: tuple[PinnedFile, ...], *, contents: dict[str, bytes]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for pinned in files:
        if pinned.name in contents:
            (directory / pinned.name).write_bytes(contents[pinned.name])


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch) -> tuple[PinnedFile, ...]:
    """A two-file asset the test owns, standing in for the real pin."""
    payloads = {"weights.bin": b"the weights", "vocabulary.json": b"the vocabulary"}
    files = tuple(
        PinnedFile(name, hashlib.sha256(payload).hexdigest())
        for name, payload in payloads.items()
    )
    monkeypatch.setattr(asset, "MODEL_FILES", files)
    return files


def _payload(name: str) -> bytes:
    return {"weights.bin": b"the weights", "vocabulary.json": b"the vocabulary"}[name]


def test_an_intact_install_reports_no_failures(tmp_path: Path, pinned: tuple[PinnedFile, ...]) -> None:
    _install(tmp_path, pinned, contents={p.name: _payload(p.name) for p in pinned})
    assert integrity_failures(tmp_path) == ()


def test_a_missing_file_is_named(tmp_path: Path, pinned: tuple[PinnedFile, ...]) -> None:
    _install(tmp_path, pinned, contents={"weights.bin": _payload("weights.bin")})
    failures = integrity_failures(tmp_path)
    assert len(failures) == 1
    assert "vocabulary.json" in failures[0]
    assert "missing" in failures[0]


def test_a_tampered_file_is_named_with_both_digests(tmp_path: Path, pinned: tuple[PinnedFile, ...]) -> None:
    contents = {p.name: _payload(p.name) for p in pinned}
    contents["weights.bin"] = b"not the weights"
    _install(tmp_path, pinned, contents=contents)
    failures = integrity_failures(tmp_path)
    assert len(failures) == 1
    assert hashlib.sha256(b"not the weights").hexdigest() in failures[0]
    assert next(p.sha256 for p in pinned if p.name == "weights.bin") in failures[0]


def test_every_problem_is_reported_not_only_the_first(tmp_path: Path, pinned: tuple[PinnedFile, ...]) -> None:
    """An operator fixing an install wants the whole list, not one round trip per file."""
    _install(tmp_path, pinned, contents={"weights.bin": b"corrupt"})
    failures = integrity_failures(tmp_path)
    assert len(failures) == 2


def test_an_empty_directory_reports_every_file_missing(tmp_path: Path, pinned: tuple[PinnedFile, ...]) -> None:
    assert len(integrity_failures(tmp_path)) == len(pinned)


def test_presence_is_checked_without_hashing(
    tmp_path: Path, pinned: tuple[PinnedFile, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`installed_model_directory` is the cheap question; hashing 30 MB is the expensive one."""
    monkeypatch.setenv(ENV_MODEL_DIRECTORY, str(tmp_path))
    monkeypatch.setattr(asset, "sha256_hex", lambda data: pytest.fail("hashed during a presence check"))
    _install(tmp_path, pinned, contents={p.name: b"contents that would not verify" for p in pinned})
    assert installed_model_directory() == tmp_path


def test_a_partial_install_is_not_reported_as_installed(
    tmp_path: Path, pinned: tuple[PinnedFile, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_MODEL_DIRECTORY, str(tmp_path))
    _install(tmp_path, pinned, contents={"weights.bin": _payload("weights.bin")})
    assert installed_model_directory() is None


def test_the_environment_names_a_shared_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Several checkouts on one machine should not each carry 31 MB."""
    monkeypatch.setenv(ENV_MODEL_DIRECTORY, str(tmp_path))
    assert model_directory() == tmp_path


def test_without_the_environment_the_location_sits_under_the_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_MODEL_DIRECTORY, raising=False)
    directory = model_directory()
    assert (directory.parent.parent / "pyproject.toml").exists()
    assert directory.name


def test_every_pinned_file_is_addressed_by_revision_not_by_branch() -> None:
    """A tag or branch can be moved under a pin; a commit cannot."""
    for pinned_file in MODEL_FILES:
        url = file_url(pinned_file)
        assert MODEL_REVISION in url
        assert url.endswith(pinned_file.name)
        assert "/main/" not in url


def test_every_pinned_digest_is_a_full_sha256() -> None:
    """A truncated or placeholder pin would compare unequal to everything, but say so obscurely."""
    for pinned_file in MODEL_FILES:
        assert len(pinned_file.sha256) == 64
        assert pinned_file.sha256 == pinned_file.sha256.lower()
        int(pinned_file.sha256, 16)
