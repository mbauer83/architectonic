"""`arch-assurance seed`: bundle-declared signal anchors, fail-before-mutate on a
--with-signals run that cannot ingest, and the shipped seed bundle's integrity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.cli._seed_commands import (
    DEFAULT_SEED_FILENAME,
    SEED_REPO_SUBDIR,
    SignalAnchor,
    cmd_seed,
    parse_signal_anchors,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
#: The shipped bundle lives in the repository it describes, not at the workspace root.
SHIPPED_SEED = (
    REPO_ROOT / "engagements" / "ENG-ARCH-REPO" / "architecture-repository"
    / SEED_REPO_SUBDIR / DEFAULT_SEED_FILENAME
)


def _args(**overrides: Any) -> argparse.Namespace:
    base = {
        "input": None, "with_signals": False, "keep_existing": False,
        "db_path": None, "osv_base_url": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


class TestParseSignalAnchors:
    def test_absent_block_is_no_anchors_not_an_error(self) -> None:
        assert parse_signal_anchors({"nodes": []}) == []

    def test_entries_are_parsed_in_order(self) -> None:
        anchors = parse_signal_anchors({"signal_anchors": [
            {"anchor_entity_id": "APP@1.aaa", "target": "python", "label": "Backend"},
            {"anchor_entity_id": "APP@2.bbb", "target": "npm"},
        ]})
        assert anchors == [
            SignalAnchor("APP@1.aaa", "python", "Backend"),
            SignalAnchor("APP@2.bbb", "npm", ""),
        ]

    @pytest.mark.parametrize("block, expected", [
        ({"signal_anchors": "python"}, "must be a list"),
        ({"signal_anchors": ["APP@1.aaa"]}, "must be an object"),
        ({"signal_anchors": [{"target": "python"}]}, "missing anchor_entity_id"),
        ({"signal_anchors": [{"anchor_entity_id": "APP@1.aaa"}]}, "missing target"),
    ])
    def test_a_malformed_entry_is_an_error_never_a_silent_skip(
        self, block: dict[str, Any], expected: str,
    ) -> None:
        """Skipping would leave an anchor with no snapshot while the run reported
        success — indistinguishable from a clean ingest."""
        with pytest.raises(ValueError, match=expected):
            parse_signal_anchors(block)


class TestSeedCommand:
    def test_missing_bundle_is_reported_not_raised(self, tmp_path: Path) -> None:
        assert cmd_seed(_args(input=str(tmp_path / "nope.json"))) == 1

    def test_with_signals_without_declared_anchors_fails_before_mutating(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The model import must NOT run: reporting a successful seed while
        ingesting nothing is the failure mode this guard exists for."""
        bundle = tmp_path / "seed.json"
        bundle.write_text(json.dumps({"nodes": [], "edges": [], "arch_refs": []}))

        assert cmd_seed(_args(input=str(bundle), with_signals=True)) == 1
        assert "signal_anchors" in capsys.readouterr().err

    def test_malformed_anchor_block_fails_before_mutating(self, tmp_path: Path) -> None:
        bundle = tmp_path / "seed.json"
        bundle.write_text(json.dumps({
            "nodes": [], "signal_anchors": [{"target": "python"}],
        }))

        assert cmd_seed(_args(input=str(bundle), with_signals=True)) == 1


class TestShippedSeedBundle:
    """The bundle callers actually get. Its anchors are the contract between the
    seed and the GUI, so they are asserted here rather than assumed."""

    @pytest.fixture()
    def bundle(self) -> dict[str, Any]:
        return json.loads(SHIPPED_SEED.read_text())

    def test_declares_parseable_anchors_for_both_dogfooding_targets(
        self, bundle: dict[str, Any],
    ) -> None:
        anchors = parse_signal_anchors(bundle)
        assert {a.target for a in anchors} == {"python", "npm"}
        assert all(a.label for a in anchors), "each anchor should be human-identifiable"

    def test_anchor_ids_are_in_stable_slug_free_form(self, bundle: dict[str, Any]) -> None:
        """The slug is rename-volatile; anchor_key() normalizes to this form, so
        storing the full id here would merely be normalized away."""
        from src.domain.assurance.security_signal_snapshot import anchor_key

        for anchor in parse_signal_anchors(bundle):
            assert anchor.anchor_entity_id == anchor_key(anchor.anchor_entity_id)

    def test_targets_are_all_supported(self, bundle: dict[str, Any]) -> None:
        from src.infrastructure.assurance.signal_sources import SBOM_TARGETS

        for anchor in parse_signal_anchors(bundle):
            assert anchor.target in SBOM_TARGETS

    def test_graph_is_referentially_closed(self, bundle: dict[str, Any]) -> None:
        """A dangling edge or arch_ref would seed a broken graph."""
        node_ids = {n["node_id"] for n in bundle["nodes"]}
        for edge in bundle["edges"]:
            assert edge["source_id"] in node_ids, edge["edge_id"]
            assert edge["target_id"] in node_ids, edge["edge_id"]
        for ref in bundle["arch_refs"]:
            assert ref["assurance_node_id"] in node_ids

    def test_arch_refs_point_at_artifacts_that_exist(self, bundle: dict[str, Any]) -> None:
        """Seeding references to deleted entities would create dangling bindings."""
        roots = [REPO_ROOT / "engagements", REPO_ROOT / "enterprise-repository"]
        for artifact_id in sorted({r["arch_artifact_id"] for r in bundle["arch_refs"]}):
            found = any(
                any(root.rglob(f"{artifact_id}*.md")) for root in roots if root.is_dir()
            )
            assert found, f"seed arch_ref targets a missing artifact: {artifact_id}"
