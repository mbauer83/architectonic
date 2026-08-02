"""One file per artifact, in a directory named by the artifact's type hierarchy.

`entity_path` is where the requirement that artifacts are *files in a navigable tree* actually holds
or fails, and nothing tested it directly — the layout was only ever asserted incidentally, by tests
that wrote an entity and then read back a path they had themselves constructed the same way.

The claim has three parts and each is a separate assertion below: a **single** file per artifact (not
a directory, not a pair), **named by the artifact id** so a directory listing is an index, and placed
under the **type hierarchy** so the tree is the organisation rather than a flat dump.

Both layouts, because both ship: an ungrouped artifact lands under `model/`, and one belonging to a
model-project lands under `projects/<group>/model/`. A test covering only the first would let the
group-aware path drift, and that is the one every new repository uses.

verifies: REQ@1712870400.vlMSrd  (file-based artifacts, organised by type and sub-type)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.ontology_representation.ontology_types import EntityTypeInfo
from src.domain.repository.groups import UNCATEGORIZED
from src.infrastructure.write.artifact_write.entity import entity_path

REPO = Path("/w/engagements/ENG-X/architecture-repository")
ENTITY_ID = "APP@1700000000.aB3dEf.payments-service"


@pytest.fixture()
def component() -> EntityTypeInfo:
    """A real shipped type, so the hierarchy under test is the product's rather than a fixture's."""
    from src.infrastructure.app_bootstrap import get_module_registry

    for info in get_module_registry().all_entity_types().values():
        if len(info.hierarchy) >= 2:
            return info
    pytest.fail("no shipped entity type has a two-level hierarchy to lay out")


def test_an_artifact_is_one_file_named_by_its_id(component: EntityTypeInfo) -> None:
    path = entity_path(REPO, component, ENTITY_ID)
    assert path.suffix == ".md", path
    assert path.stem == ENTITY_ID, path
    # One file, not a directory holding parts: the whole artifact is the file.
    assert path.name == f"{ENTITY_ID}.md"


def test_the_directory_is_the_type_hierarchy(component: EntityTypeInfo) -> None:
    """"Organized by types and sub-types" — the hierarchy, in order, as directories."""
    path = entity_path(REPO, component, ENTITY_ID)
    assert path.parent.parts[-len(component.hierarchy):] == tuple(component.hierarchy), path


def test_an_ungrouped_artifact_lands_under_the_repository_model_root(component: EntityTypeInfo) -> None:
    path = entity_path(REPO, component, ENTITY_ID, UNCATEGORIZED)
    assert "model" in path.parts, path
    assert "projects" not in path.parts, path
    assert path.is_relative_to(REPO), path


def test_a_grouped_artifact_lands_under_its_model_project(component: EntityTypeInfo) -> None:
    # Read off `parent.parts`, so the filename does not shift the window the hierarchy sits in.
    directories = entity_path(REPO, component, ENTITY_ID, "payments").parent.parts
    depth = len(component.hierarchy)
    assert directories[-depth:] == tuple(component.hierarchy), directories
    assert directories[-depth - 3:-depth] == ("projects", "payments", "model"), directories


def test_two_artifacts_of_one_type_are_siblings_rather_than_nested(component: EntityTypeInfo) -> None:
    # Navigability is the point of the layout: everything of a type is listable in one directory.
    other = "APP@1700000001.zZ9yXw.billing-service"
    assert entity_path(REPO, component, ENTITY_ID).parent == entity_path(REPO, component, other).parent


def test_the_group_and_ungrouped_layouts_differ_only_by_the_project_segments(
    component: EntityTypeInfo,
) -> None:
    """Same type directory, same filename — so moving an artifact between groups is a move, not a
    rename, and a reader's mental model of "where does an application component live" survives it."""
    ungrouped = entity_path(REPO, component, ENTITY_ID, UNCATEGORIZED)
    grouped = entity_path(REPO, component, ENTITY_ID, "payments")
    assert ungrouped.name == grouped.name
    tail = len(component.hierarchy) + 1
    assert ungrouped.parts[-tail:] == grouped.parts[-tail:]
