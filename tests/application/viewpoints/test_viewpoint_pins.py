"""Tests for the viewpoint-pins sidecar: absence, CRUD round-trip, deduplication, and
read-time pruning of slugs no longer in the known set."""

from __future__ import annotations

from pathlib import Path

from src.application.viewpoints.pins import load_pinned_slugs, save_pinned_slugs
from src.domain.repository.repo_layout import ARCH_REPO


class TestAbsence:
    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        result = load_pinned_slugs(tmp_path, known_slugs=frozenset({"a"}))
        assert result.slugs == ()
        assert result.pruned == ()


class TestRoundTrip:
    def test_save_then_load_round_trips(self, tmp_path: Path) -> None:
        save_pinned_slugs(tmp_path, ("alpha", "beta"))
        result = load_pinned_slugs(tmp_path, known_slugs=frozenset({"alpha", "beta"}))
        assert result.slugs == ("alpha", "beta")
        assert result.pruned == ()

    def test_save_deduplicates_preserving_first_occurrence_order(self, tmp_path: Path) -> None:
        save_pinned_slugs(tmp_path, ("beta", "alpha", "beta"))
        text = (tmp_path / ARCH_REPO / "viewpoint-pins.yaml").read_text(encoding="utf-8")
        assert "beta" in text and "alpha" in text
        result = load_pinned_slugs(tmp_path, known_slugs=frozenset({"alpha", "beta"}))
        assert result.slugs == ("beta", "alpha")

    def test_save_empty_list_clears_pins(self, tmp_path: Path) -> None:
        save_pinned_slugs(tmp_path, ("alpha",))
        save_pinned_slugs(tmp_path, ())
        result = load_pinned_slugs(tmp_path, known_slugs=frozenset({"alpha"}))
        assert result.slugs == ()


class TestPruning:
    def test_unknown_slugs_are_pruned_and_reported(self, tmp_path: Path) -> None:
        save_pinned_slugs(tmp_path, ("alpha", "ghost", "beta"))
        result = load_pinned_slugs(tmp_path, known_slugs=frozenset({"alpha", "beta"}))
        assert result.slugs == ("alpha", "beta")
        assert result.pruned == ("ghost",)

    def test_pruning_does_not_rewrite_the_file(self, tmp_path: Path) -> None:
        save_pinned_slugs(tmp_path, ("alpha", "ghost"))
        load_pinned_slugs(tmp_path, known_slugs=frozenset({"alpha"}))
        text = (tmp_path / ARCH_REPO / "viewpoint-pins.yaml").read_text(encoding="utf-8")
        assert "ghost" in text
