"""Directness needs a BOM ROOT, not just a dependency graph.

Regression: `cyclonedx-py environment` emits the full dependency graph but no
``metadata.component``. ``classify_directness`` measures depth FROM the root, so
without one every component classifies as "unknown" — a snapshot that reads like
a successful scan while carrying no directness information at all. The fix is the
generator's ``--pyproject`` flag; these tests pin the property it buys, at the
parser level (no subprocess) plus the command construction itself.
"""

from __future__ import annotations

import collections
from pathlib import Path
from typing import Any

from src.application.security_signals.bundle_assembly import prepare_components
from src.infrastructure.assurance._sbom_parser import parse_bom

_COMPONENTS: list[dict[str, Any]] = [
    {"bom-ref": "a==1", "name": "a", "version": "1", "purl": "pkg:pypi/a@1"},
    {"bom-ref": "b==1", "name": "b", "version": "1", "purl": "pkg:pypi/b@1"},
    {"bom-ref": "c==1", "name": "c", "version": "1", "purl": "pkg:pypi/c@1"},
]
_DEPENDENCIES: list[dict[str, Any]] = [
    {"ref": "root-component", "dependsOn": ["a==1"]},
    {"ref": "a==1", "dependsOn": ["b==1"]},
    {"ref": "b==1"},
    {"ref": "c==1"},
]


def _bom(*, with_root: bool) -> dict[str, Any]:
    bom: dict[str, Any] = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:root-test",
        "version": 1,
        "components": list(_COMPONENTS),
        "dependencies": list(_DEPENDENCIES),
    }
    if with_root:
        bom["metadata"] = {"component": {
            "bom-ref": "root-component", "name": "app", "version": "0.1.0",
        }}
    return bom


def _directness(bom: dict[str, Any]) -> dict[str, int]:
    meta, parsed = parse_bom(bom)
    assembled = prepare_components(meta, parsed)
    return dict(collections.Counter(
        str(c.get("directness")) for c in assembled.components))


class TestRootComponentDrivesDirectness:
    def test_without_a_root_every_component_is_unknown(self) -> None:
        """The graph alone is not enough — this is the silent-degradation case."""
        assert _directness(_bom(with_root=False)) == {"unknown": 3}

    def test_with_a_root_depth_is_classified(self) -> None:
        distribution = _directness(_bom(with_root=True))

        # a is depth 1, b is depth 2, c is unreachable, root itself is not a
        # dependency of itself.
        assert distribution["direct"] == 1
        assert distribution["transitive"] == 1
        assert distribution["unknown"] == 2

    def test_the_parser_only_reports_a_root_when_one_is_present(self) -> None:
        assert parse_bom(_bom(with_root=False))[0].get("root_bom_ref") is None
        assert parse_bom(_bom(with_root=True))[0]["root_bom_ref"] == "root-component"

    def test_the_dependency_graph_is_read_either_way(self) -> None:
        """Isolates the cause: the edges were never the missing piece — the graph
        parses identically with and without a root; only the reference point for
        measuring depth is absent."""
        without = parse_bom(_bom(with_root=False))[0]["dependencies"]
        with_root = parse_bom(_bom(with_root=True))[0]["dependencies"]

        assert without == with_root
        assert [entry for entry in without if entry["depends_on"]] != []


class TestPythonGeneratorRequestsARoot:
    def test_pyproject_is_passed_so_the_bom_has_a_root(
        self, tmp_path: Path, monkeypatch: Any,
    ) -> None:
        from src.infrastructure.assurance import signal_sources

        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        seen: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path | None = None) -> str:
            seen.append(command)
            return "1.0" if "--version" in command else "{}"

        monkeypatch.setattr(signal_sources, "_run", fake_run)
        signal_sources.generate_python_sbom(tmp_path)

        generate = seen[-1]
        assert "--pyproject" in generate
        assert generate[generate.index("--pyproject") + 1] == str(tmp_path / "pyproject.toml")

    def test_a_missing_pyproject_warns_rather_than_degrading_silently(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any,
    ) -> None:
        from src.infrastructure.assurance import signal_sources

        monkeypatch.setattr(
            signal_sources, "_run",
            lambda command, cwd=None: "1.0" if "--version" in command else "{}")
        signal_sources.generate_python_sbom(tmp_path)

        assert "unknown" in capsys.readouterr().err
