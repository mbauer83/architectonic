"""The verify tool refuses an unconfirmed full pass, and the refusal is cheap and informative."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.infrastructure.mcp.artifact_mcp import verify_tools


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository with no prior verification state — the 'first run' trigger."""
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    monkeypatch.setenv("ARCH_MODEL_VERIFY_STATE_DIR", str(tmp_path / "verify-state"))
    monkeypatch.delenv("ARCH_MODEL_VERIFY_MODE", raising=False)
    return root


class TestAnUnconfirmedFullPassIsRefused:
    def test_the_refusal_names_the_reason_and_the_size(self, repo: Path) -> None:
        out = verify_tools.artifact_verify(repo_root=str(repo), repo_scope="engagement")

        assert out["results"] == []
        assert set(out["pass_mode"].values()) == {"full-required"}
        assert "no prior verification state" in " ".join(out["full_pass_required"].values())
        assert list(out["files_to_verify"].values()) == [0]
        assert "confirm_full_pass=true" in out["message"]

    def test_the_refusal_is_immediate(self, repo: Path) -> None:
        """The point of the control: an answer in milliseconds instead of a timeout."""
        started = time.monotonic()
        verify_tools.artifact_verify(repo_root=str(repo), repo_scope="engagement")

        assert time.monotonic() - started < 5.0

    def test_confirming_proceeds(self, repo: Path) -> None:
        out = verify_tools.artifact_verify(
            repo_root=str(repo), repo_scope="engagement", confirm_full_pass=True
        )

        assert "full_pass_required" not in out
        assert set(out["pass_mode"].values()) == {"full"}

    def test_configuration_is_consent(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """CI and `arch-repair` cannot re-call, so the env override must still imply consent."""
        monkeypatch.setenv("ARCH_MODEL_VERIFY_MODE", "full")

        out = verify_tools.artifact_verify(repo_root=str(repo), repo_scope="engagement")

        assert "full_pass_required" not in out
        assert set(out["pass_mode"].values()) == {"full"}

    def test_a_single_file_verify_is_never_refused(self, repo: Path) -> None:
        """The control is about whole-repository cost; one file has none."""
        target = repo / "model" / "nothing-here.md"
        target.write_text("---\nartifact-id: X\n---\n", encoding="utf-8")

        out = verify_tools.artifact_verify(path=str(target), repo_root=str(repo), repo_scope="engagement")

        assert "full_pass_required" not in out

    def test_a_reusable_cache_is_not_refused(self, repo: Path) -> None:
        verify_tools.artifact_verify(repo_root=str(repo), repo_scope="engagement", confirm_full_pass=True)

        out = verify_tools.artifact_verify(repo_root=str(repo), repo_scope="engagement")

        assert "full_pass_required" not in out
        assert set(out["pass_mode"].values()) == {"incremental-cached"}
