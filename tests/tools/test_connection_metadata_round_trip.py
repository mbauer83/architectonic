"""WU-W3: per-connection metadata beyond ``specialization`` — the attributes a connection
type's effective metadata schema declares — must be writable AND survive a reformat.

The regression this pins: the parsed connection dict used to carry only ``specialization``
out of the metadata block, so any edit that reformatted the file silently dropped every
other declared attribute. A schema-driven connection metadata editor would have made that
data loss routine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.modeling.artifact_write import format_outgoing_markdown
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.connection import add_connection
from src.infrastructure.write.artifact_write.connection_edit import edit_connection
from src.infrastructure.write.artifact_write.entity import create_entity
from src.infrastructure.write.artifact_write.parse_existing import parse_outgoing_file

_CONNECTION_TYPE = "archimate-assignment"


def _eng_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-META" / "architecture-repository"
    root.mkdir(parents=True)
    return root


def _registry(repo_root: Path) -> ArtifactRegistry:
    index = shared_artifact_index([repo_root])
    index.refresh()
    return ArtifactRegistry(index)


def _verifier(registry: ArtifactRegistry) -> ArtifactVerifier:
    return ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))


@pytest.fixture()
def connected(tmp_path: Path) -> tuple[Path, str, str]:
    root = _eng_root(tmp_path)
    ids = []
    for name in ("Meta Source", "Meta Target"):
        registry = _registry(root)
        ids.append(
            create_entity(
                repo_root=root, verifier=_verifier(registry), clear_repo_caches=lambda p: None,
                artifact_type="role", name=name, summary=None, properties=None,
                notes=None, specialization=None, artifact_id=None, version="0.1.0", status="draft",
                last_updated=None, dry_run=False,
            ).artifact_id
        )
    return root, ids[0], ids[1]


def _add(root: Path, source: str, target: str, **kwargs: object) -> None:
    registry = _registry(root)
    add_connection(
        repo_root=root, registry=registry, verifier=_verifier(registry),
        clear_repo_caches=lambda p: None, source_entity=source, connection_type=_CONNECTION_TYPE,
        target_entity=target, description=None, version="0.1.0", status="draft",
        last_updated=None, dry_run=False, **kwargs,
    )


def _metadata_of(root: Path, source: str) -> dict[str, object]:
    outgoing = next(root.rglob(f"{source}.outgoing.md"))
    conn = parse_outgoing_file(outgoing).connections[0]
    raw = conn.get("metadata")
    return dict(raw) if isinstance(raw, dict) else {}


class TestFormatting:
    def test_metadata_block_survives_a_reformat(self) -> None:
        text = format_outgoing_markdown(
            source_entity="APP-001", version="0.1.0", status="draft", last_updated="2026-07-22",
            connections=[{
                "connection_type": _CONNECTION_TYPE, "target_entity": "APP-002", "description": "",
                "metadata": {"cadence": "weekly", "specialization": "responsibility-assignment"},
                "specialization": "responsibility-assignment",
            }],
        )
        assert "cadence: weekly" in text
        assert "specialization: responsibility-assignment" in text

    def test_clearing_the_specialization_leaves_the_other_attributes(self) -> None:
        text = format_outgoing_markdown(
            source_entity="APP-001", version="0.1.0", status="draft", last_updated="2026-07-22",
            connections=[{
                "connection_type": _CONNECTION_TYPE, "target_entity": "APP-002", "description": "",
                "metadata": {"cadence": "weekly", "specialization": "responsibility-assignment"},
            }],
        )
        assert "cadence: weekly" in text
        assert "specialization:" not in text


class TestWritePath:
    def test_add_persists_metadata(self, connected: tuple[Path, str, str]) -> None:
        root, source, target = connected
        _add(root, source, target, metadata={"cadence": "weekly"})
        assert _metadata_of(root, source)["cadence"] == "weekly"

    def test_add_persists_metadata_alongside_a_specialization(self, connected: tuple[Path, str, str]) -> None:
        root, source, target = connected
        _add(root, source, target, specialization="responsibility-assignment", metadata={"cadence": "weekly"})
        block = _metadata_of(root, source)
        assert block["cadence"] == "weekly"
        assert block["specialization"] == "responsibility-assignment"

    def test_an_unrelated_edit_preserves_metadata(self, connected: tuple[Path, str, str]) -> None:
        # The regression: editing only the description used to drop `cadence` entirely.
        root, source, target = connected
        _add(root, source, target, metadata={"cadence": "weekly"})
        registry = _registry(root)
        edit_connection(
            repo_root=root, registry=registry, verifier=_verifier(registry),
            clear_repo_caches=lambda p: None, source_entity=source, target_entity=target,
            connection_type=_CONNECTION_TYPE, description="now described", dry_run=False,
        )
        assert _metadata_of(root, source)["cadence"] == "weekly"

    def test_edit_patches_metadata_key_by_key(self, connected: tuple[Path, str, str]) -> None:
        """Mirrors the entity edit API's `properties`: only sent keys change."""
        root, source, target = connected
        _add(root, source, target, metadata={"cadence": "weekly", "owner": "platform"})
        registry = _registry(root)
        edit_connection(
            repo_root=root, registry=registry, verifier=_verifier(registry),
            clear_repo_caches=lambda p: None, source_entity=source, target_entity=target,
            connection_type=_CONNECTION_TYPE, metadata={"cadence": "daily"}, dry_run=False,
        )
        block = _metadata_of(root, source)
        assert block["cadence"] == "daily"
        assert block["owner"] == "platform"  # untouched keys survive a patch

    def test_edit_removes_a_key_mapped_to_none(self, connected: tuple[Path, str, str]) -> None:
        root, source, target = connected
        _add(root, source, target, metadata={"cadence": "weekly", "owner": "platform"})
        registry = _registry(root)
        edit_connection(
            repo_root=root, registry=registry, verifier=_verifier(registry),
            clear_repo_caches=lambda p: None, source_entity=source, target_entity=target,
            connection_type=_CONNECTION_TYPE, metadata={"owner": None}, dry_run=False,
        )
        block = _metadata_of(root, source)
        assert "owner" not in block
        assert block["cadence"] == "weekly"

    def test_edit_can_clear_metadata(self, connected: tuple[Path, str, str]) -> None:
        """None for the whole parameter clears every attribute ({} is a no-op patch)."""
        root, source, target = connected
        _add(root, source, target, metadata={"cadence": "weekly"})
        registry = _registry(root)
        edit_connection(
            repo_root=root, registry=registry, verifier=_verifier(registry),
            clear_repo_caches=lambda p: None, source_entity=source, target_entity=target,
            connection_type=_CONNECTION_TYPE, metadata=None, dry_run=False,
        )
        assert _metadata_of(root, source) == {}
