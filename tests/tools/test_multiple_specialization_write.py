"""WU-V4: the entity and connection write paths accept multiple specializations and
serialize them faithfully — one as a scalar (byte-identical to existing files), several as a
list (§15.2) — round-tripping through the parser.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from src.application.artifact_parsing import parse_entity, parse_outgoing_file
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index.service import ArtifactIndex
from src.infrastructure.write.artifact_write.connection import add_connection
from src.infrastructure.write.artifact_write.entity import create_entity
from src.infrastructure.write.artifact_write.entity_edit import edit_entity

_SPECS_YAML = """\
specializations:
  entity:
    collaboration:
      - {slug: business-collaboration, name: Business Collaboration}
      - {slug: application-collaboration, name: Application Collaboration}
  connection:
    archimate-assignment:
      - {slug: responsibility-assignment, name: Responsibility Assignment}
      - {slug: behavior-assignment, name: Behavior Assignment}
"""


def _eng_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-MULTI" / "architecture-repository"
    root.mkdir(parents=True)
    (root / ".arch-repo").mkdir()
    (root / ".arch-repo" / "specializations.yaml").write_text(_SPECS_YAML, encoding="utf-8")
    return root


def _deps(root: Path) -> tuple[ArtifactRegistry, ArtifactVerifier]:
    registry = ArtifactRegistry(ArtifactIndex([root]))
    return registry, ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))


def _frontmatter_specialization(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    block = text.split("---", 2)[1]
    return yaml.safe_load(block).get("specialization")


class TestEntityWrite:
    def test_create_with_several_writes_a_list(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path)
        registry, verifier = _deps(root)
        result = create_entity(
            repo_root=root, verifier=verifier, clear_repo_caches=lambda p: None,
            artifact_type="collaboration", name="Cross Team", summary=None, properties=None,
            notes=None, specializations=["business-collaboration", "application-collaboration"],
            artifact_id=None, version="0.1.0", status="draft", last_updated=None, dry_run=False,
        )
        path = next(root.rglob(f"{result.artifact_id}.md"))
        assert _frontmatter_specialization(path) == ["business-collaboration", "application-collaboration"]
        assert parse_entity(
            path, root, domain_names=frozenset({"business"})
        ).specializations == ("business-collaboration", "application-collaboration")

    def test_create_with_one_writes_a_scalar(self, tmp_path: Path) -> None:
        # Byte-compat: a single specialization must stay a scalar so existing repos are unchanged.
        root = _eng_root(tmp_path)
        registry, verifier = _deps(root)
        result = create_entity(
            repo_root=root, verifier=verifier, clear_repo_caches=lambda p: None,
            artifact_type="collaboration", name="Solo", summary=None, properties=None,
            notes=None, specializations=["business-collaboration"],
            artifact_id=None, version="0.1.0", status="draft", last_updated=None, dry_run=False,
        )
        path = next(root.rglob(f"{result.artifact_id}.md"))
        assert _frontmatter_specialization(path) == "business-collaboration"

    def test_edit_replaces_the_whole_set(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path)
        registry, verifier = _deps(root)
        created = create_entity(
            repo_root=root, verifier=verifier, clear_repo_caches=lambda p: None,
            artifact_type="collaboration", name="Editable", summary=None, properties=None,
            notes=None, specialization="business-collaboration",
            artifact_id=None, version="0.1.0", status="draft", last_updated=None, dry_run=False,
        )
        registry, verifier = _deps(root)
        edit_entity(
            repo_root=root, registry=registry, verifier=verifier, clear_repo_caches=lambda p: None,
            artifact_id=created.artifact_id,
            specializations=["business-collaboration", "application-collaboration"], dry_run=False,
        )
        path = next(root.rglob(f"{created.artifact_id}.md"))
        assert _frontmatter_specialization(path) == ["business-collaboration", "application-collaboration"]


class TestConnectionWrite:
    def test_add_with_several_writes_a_list(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path)
        ids = []
        for name in ("Role A", "Role B"):
            registry, verifier = _deps(root)
            ids.append(
                create_entity(
                    repo_root=root, verifier=verifier, clear_repo_caches=lambda p: None,
                    artifact_type="role", name=name, summary=None, properties=None, notes=None,
                    specialization=None, artifact_id=None, version="0.1.0", status="draft",
                    last_updated=None, dry_run=False,
                ).artifact_id
            )
        registry, verifier = _deps(root)
        add_connection(
            repo_root=root, registry=registry, verifier=verifier, clear_repo_caches=lambda p: None,
            source_entity=ids[0], connection_type="archimate-assignment", target_entity=ids[1],
            description=None, version="0.1.0", status="draft", last_updated=None, dry_run=False,
            specializations=["responsibility-assignment", "behavior-assignment"],
        )
        outgoing = next(root.rglob(f"{ids[0]}.outgoing.md"))
        conn = parse_outgoing_file(outgoing)[0]
        assert conn.specializations == ("responsibility-assignment", "behavior-assignment")


@pytest.mark.parametrize("count", [1, 2])
def test_round_trip_preserves_order(tmp_path: Path, count: int) -> None:
    root = _eng_root(tmp_path)
    registry, verifier = _deps(root)
    applied = ["application-collaboration", "business-collaboration"][:count]
    result = create_entity(
        repo_root=root, verifier=verifier, clear_repo_caches=lambda p: None,
        artifact_type="collaboration", name="Ordered", summary=None, properties=None,
        notes=None, specializations=applied, artifact_id=None, version="0.1.0", status="draft",
        last_updated=None, dry_run=False,
    )
    path = next(root.rglob(f"{result.artifact_id}.md"))
    assert parse_entity(path, root, domain_names=frozenset({"business"})).specializations == tuple(applied)
