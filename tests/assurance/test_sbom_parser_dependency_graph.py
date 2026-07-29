"""SBOM parser preservation contract (D13): bom-ref on every component, the
metadata root flagged (never treated as a dependency), and the dependency
graph normalized — for CycloneDX and SPDX."""

from __future__ import annotations

from src.domain.assurance.security_signal_snapshot import classify_directness
from src.infrastructure.assurance._sbom_parser import parse_bom

CDX = {
    "bomFormat": "CycloneDX",
    "serialNumber": "urn:uuid:1234",
    "version": 2,
    "metadata": {
        "component": {"bom-ref": "root-app", "name": "arch-repo", "type": "application"},
    },
    "components": [
        {"bom-ref": "ref-a", "purl": "pkg:pypi/a@1", "name": "a", "version": "1"},
        {"bom-ref": "ref-b", "purl": "pkg:pypi/b@2", "name": "b", "version": "2"},
    ],
    "dependencies": [
        {"ref": "root-app", "dependsOn": ["ref-a"]},
        {"ref": "ref-a", "dependsOn": ["ref-b"]},
    ],
}

SPDX = {
    "spdxVersion": "SPDX-2.3",
    "SPDXID": "SPDXRef-DOCUMENT",
    "packages": [
        {"SPDXID": "SPDXRef-a", "name": "a", "versionInfo": "1"},
        {"SPDXID": "SPDXRef-b", "name": "b", "versionInfo": "2"},
    ],
    "relationships": [
        {"spdxElementId": "SPDXRef-a", "relatedSpdxElement": "SPDXRef-b",
         "relationshipType": "DEPENDS_ON"},
        {"spdxElementId": "SPDXRef-a", "relatedSpdxElement": "SPDXRef-b",
         "relationshipType": "CONTAINS"},  # not a dependency edge
    ],
}


class TestCycloneDx:
    def test_bom_refs_and_root_flag_are_preserved(self) -> None:
        meta, components = parse_bom(CDX)
        by_ref = {c["bom_ref"]: c for c in components}
        assert set(by_ref) == {"root-app", "ref-a", "ref-b"}
        assert by_ref["root-app"]["is_root"] is True
        assert by_ref["ref-a"]["is_root"] is False
        assert meta["root_bom_ref"] == "root-app"

    def test_dependency_graph_survives_normalization(self) -> None:
        meta, _ = parse_bom(CDX)
        assert meta["dependencies"] == [
            {"ref": "root-app", "depends_on": ["ref-a"]},
            {"ref": "ref-a", "depends_on": ["ref-b"]},
        ]

    def test_directness_classification_works_from_parsed_output(self) -> None:
        meta, _ = parse_bom(CDX)
        edges = [
            (str(entry["ref"]), str(target))
            for entry in meta["dependencies"]  # type: ignore[union-attr]
            for target in entry["depends_on"]  # type: ignore[index]
        ]
        root = str(meta["root_bom_ref"])
        assert classify_directness(root, "ref-a", edges) == "direct"
        assert classify_directness(root, "ref-b", edges) == "transitive"
        assert classify_directness(root, root, edges) == "unknown"


class TestSpdx:
    def test_bom_refs_come_from_spdx_ids(self) -> None:
        _, components = parse_bom(SPDX)
        assert [c["bom_ref"] for c in components] == ["SPDXRef-a", "SPDXRef-b"]
        assert all(c["is_root"] is False for c in components)

    def test_only_depends_on_relationships_become_edges(self) -> None:
        meta, _ = parse_bom(SPDX)
        assert meta["dependencies"] == [{"ref": "SPDXRef-a", "depends_on": ["SPDXRef-b"]}]


class TestAbsentGraph:
    def test_missing_dependencies_yield_an_empty_edge_list(self) -> None:
        meta, _ = parse_bom({"bomFormat": "CycloneDX", "components": []})
        assert meta["dependencies"] == []
