"""A kind's own id prefix is declared by nothing else that mints ids, and a collision is refused by name.

`ICO@…` is read as an icon and `SCR@…` as a scratchpad without asking any type, so each of the other
three things that mint a prefix is held against them: an entity type and a diagram type when the
module registry is built, a document type — repository data — when a repository is loaded.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from src.application import _startup_registry_consistency
from src.application._startup_kind_table_consistency import (
    catalogue_prefix_owners,
    document_type_prefix_owners,
    kind_prefix_collisions,
    kind_table_consistency_msgs,
)
from src.application.modeling.artifact_write import prefix_for_diagram_type
from src.application.startup_validation import (
    RegistryConsistencyError,
    RepoCompatibilityError,
    validate_registry_consistency,
    validate_repo_compatibility,
)
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.repository.artifact_location import ARTIFACT_KINDS, KindDeclaration, artifact_kind
from src.infrastructure.app_bootstrap import build_module_registry


@pytest.fixture(scope="module")
def product_registry() -> ModuleRegistry:
    return build_module_registry(complete_vocabulary=True)


def _icon_prefixed(prefix: str) -> tuple[KindDeclaration, ...]:
    return tuple(replace(row, id_prefix=prefix) if row.name == "icon" else row for row in ARTIFACT_KINDS)


def test_the_shipped_catalogues_claim_no_kind_s_prefix(product_registry: ModuleRegistry) -> None:
    assert list(kind_table_consistency_msgs(product_registry)) == []


def test_a_kind_prefix_an_entity_type_declares_is_refused(product_registry: ModuleRegistry) -> None:
    type_name, info = next(iter(product_registry.all_entity_types().items()))

    messages = list(kind_table_consistency_msgs(product_registry, _icon_prefixed(info.prefix)))

    assert any(
        f"Id prefix {info.prefix!r} is the icon kind's own" in message
        and f"the entity type {str(type_name)!r}" in message
        and "that declaration must take another prefix" in message
        for message in messages
    ), messages


def test_a_kind_prefix_a_diagram_type_derives_is_refused(product_registry: ModuleRegistry) -> None:
    diagram_type = str(next(iter(product_registry.all_diagram_types().values())).name)
    derived = prefix_for_diagram_type(diagram_type)

    messages = list(kind_table_consistency_msgs(product_registry, _icon_prefixed(derived)))

    assert any(f"the diagram type {diagram_type!r}, which derives it from its name" in m for m in messages), messages


def test_a_kind_prefix_a_diagram_s_own_entity_type_declares_is_refused(product_registry: ModuleRegistry) -> None:
    owners = catalogue_prefix_owners(product_registry)
    declared = [(prefix, who) for prefix, named in owners.items() for who in named if " of the diagram type " in who]
    if not declared:
        pytest.skip("no registered diagram type declares an id prefix for an entity type of its own")
    prefix, who = declared[0]

    messages = list(kind_prefix_collisions(owners, _icon_prefixed(prefix)))

    assert any(who in message for message in messages), messages


def test_a_table_that_contradicts_itself_is_refused_with_the_registry(product_registry: ModuleRegistry) -> None:
    """The rows' own contradictions travel the same door as the prefix namespace."""
    messages = list(kind_table_consistency_msgs(product_registry, _icon_prefixed("SCR")))

    assert any("'icon' and 'scratchpad' both declare the id prefix 'SCR'" in message for message in messages)


def test_building_a_registry_refuses_what_the_kind_table_check_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wiring: the check's sentences reach the error a process fails to start with."""
    monkeypatch.setattr(
        _startup_registry_consistency, "kind_table_consistency_msgs", lambda _registry: iter(["Kind table: broken."])
    )

    with pytest.raises(RegistryConsistencyError, match="Kind table: broken."):
        validate_registry_consistency(ModuleRegistry())


class _Repository:
    """What `validate_repo_compatibility` reads: the roots, and no content."""

    def __init__(self, root: Path) -> None:
        self.repo_roots = [root]

    def list_entities(self, **_: Any) -> list[Any]:
        return []

    list_connections = list_diagrams = list_entities


def _repository_declaring(tmp_path: Path, doc_types: dict[str, dict[str, Any]]) -> _Repository:
    directory = tmp_path / ".arch-repo" / "documents"
    directory.mkdir(parents=True)
    for doc_type, schema in doc_types.items():
        (directory / f"{doc_type}.json").write_text(json.dumps(schema), encoding="utf-8")
    return _Repository(tmp_path)


def test_a_repository_whose_document_types_claim_no_kind_s_prefix_loads(tmp_path: Path) -> None:
    repository = _repository_declaring(tmp_path, {"adr": {"abbreviation": "ADR"}, "spec": {}})

    assert validate_repo_compatibility(repository, ModuleRegistry()) == []  # type: ignore[arg-type]


@pytest.mark.parametrize("kind_name", [row.name for row in ARTIFACT_KINDS if row.id_prefix is not None])
def test_a_document_type_abbreviated_as_a_kind_s_prefix_is_refused(tmp_path: Path, kind_name: str) -> None:
    prefix = next(row.id_prefix for row in ARTIFACT_KINDS if row.name == kind_name)
    repository = _repository_declaring(tmp_path, {"notes": {"abbreviation": prefix}})

    with pytest.raises(RepoCompatibilityError) as refused:
        validate_repo_compatibility(repository, ModuleRegistry())  # type: ignore[arg-type]

    message = str(refused.value)
    assert f"Id prefix {prefix!r} is the {kind_name} kind's own" in message
    assert "the document type 'notes', as its `abbreviation`" in message
    assert str(tmp_path) in message


def test_a_document_type_whose_name_alone_spells_a_kind_s_prefix_is_refused(tmp_path: Path) -> None:
    """With no abbreviation a document's id takes its type's name in capitals."""
    prefix = artifact_kind("scratchpad").id_prefix
    assert prefix is not None
    repository = _repository_declaring(tmp_path, {prefix.lower(): {"name": "Scratch notes"}})

    with pytest.raises(RepoCompatibilityError, match=f"the document type '{prefix.lower()}'"):
        validate_repo_compatibility(repository, ModuleRegistry())  # type: ignore[arg-type]


def test_the_owner_map_names_every_document_type_sharing_a_prefix() -> None:
    owners = document_type_prefix_owners({"adr": "ADR", "decision": "ADR", "spec": "SPC"})

    assert len(owners["ADR"]) == 2 and len(owners["SPC"]) == 1
