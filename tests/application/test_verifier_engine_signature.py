"""The engine signature must respond to every rule module, not a hand-listed subset.

Incremental verifier state is reused whenever no repository file has changed. The signature
is the only thing that notices the *verifier* changed instead — so if it stops tracking a
rule module, an upgraded verifier silently keeps serving the previous verifier's verdict. A
newly added rule then reports nothing until some unrelated file happens to change, which is
indistinguishable from a clean repository.

A hardcoded filename list cannot hold that line: rename the modules and it goes on hashing
paths that no longer exist, failing open with no error anywhere.

The policy is exercised against a temporary directory rather than the real package. Editing
the verifier's own sources from a test would race every other test under ``-n auto``.
"""

from __future__ import annotations

from pathlib import Path

from src.application.verification import artifact_verifier_incremental as incremental
from src.application.verification.artifact_verifier_incremental import (
    source_tree_signature,
    verifier_engine_signature,
)


def _package(tmp_path: Path, **modules: str) -> Path:
    for name, body in modules.items():
        (tmp_path / f"{name}.py").write_text(body, encoding="utf-8")
    return tmp_path


class TestThePolicy:
    def test_is_stable_for_unchanged_content(self, tmp_path: Path) -> None:
        pkg = _package(tmp_path, rules="RULE = 1", parsing="X = 2")

        assert source_tree_signature(pkg) == source_tree_signature(pkg)

    def test_changes_when_any_module_changes(self, tmp_path: Path) -> None:
        pkg = _package(tmp_path, rules="RULE = 1", parsing="X = 2")
        before = source_tree_signature(pkg)

        (pkg / "parsing.py").write_text("X = 3", encoding="utf-8")

        assert source_tree_signature(pkg) != before

    def test_changes_when_a_module_is_added(self, tmp_path: Path) -> None:
        """A new rule module must invalidate cached results the moment it appears."""
        pkg = _package(tmp_path, rules="RULE = 1")
        before = source_tree_signature(pkg)

        (pkg / "extra_rules.py").write_text("RULE = 2", encoding="utf-8")

        assert source_tree_signature(pkg) != before

    def test_changes_when_a_module_is_renamed(self, tmp_path: Path) -> None:
        """The failure that made the previous implementation inert."""
        pkg = _package(tmp_path, model_verifier_rules="RULE = 1")
        before = source_tree_signature(pkg)

        (pkg / "model_verifier_rules.py").rename(pkg / "artifact_verifier_rules.py")

        assert source_tree_signature(pkg) != before

    def test_ignores_timestamps(self, tmp_path: Path) -> None:
        """A fresh checkout re-stamps mtimes; identical rules must not force a full pass."""
        pkg = _package(tmp_path, rules="RULE = 1")
        before = source_tree_signature(pkg)

        (pkg / "rules.py").touch()

        assert source_tree_signature(pkg) == before


class TestTheWiring:
    def test_the_signature_covers_the_verification_package(self) -> None:
        package_dir = Path(incremental.__file__).parent

        assert verifier_engine_signature() == source_tree_signature(package_dir)

    def test_the_package_holds_more_rule_modules_than_any_list_would_track(self) -> None:
        package_dir = Path(incremental.__file__).parent
        modules = {p.name for p in package_dir.glob("*.py")}

        assert {"_verifier_outgoing.py", "artifact_verifier_rules.py"} <= modules
        assert len(modules) > 5, f"expected the full package, found {len(modules)}"
