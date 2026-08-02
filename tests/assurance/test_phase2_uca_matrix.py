"""Tests for the uca-matrix diagram type (Phase 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.diagram_types.uca_matrix import module as uca_module


def test_module_name() -> None:
    assert str(uca_module.name) == "uca-matrix"


def test_module_class_is_assurance() -> None:
    assert uca_module.module_class == "assurance"


def test_requires_confidential_store() -> None:
    requires = list(getattr(uca_module, "requires", []))
    assert "confidential_store" in requires


def test_accepts_no_entity_types() -> None:
    from src.domain.modules.module_types import EntityTypeName

    assert uca_module.accepts_entity_type(EntityTypeName("application-component")) is False


def test_accepts_no_connection_types() -> None:
    from src.domain.modules.module_types import ConnectionTypeName

    assert uca_module.accepts_connection_type(ConnectionTypeName("archimate-composition")) is False


def test_renderer_raises_value_error() -> None:
    renderer = uca_module.renderer
    with pytest.raises(ValueError, match="UCA matrix diagrams use the markdown UCA grid renderer"):
        renderer.render_body("test", [], [], "uca-matrix", Path("/fake"))


def test_renderer_raises_regardless_of_diagram_entities() -> None:
    renderer = uca_module.renderer
    with pytest.raises(ValueError):
        renderer.render_body(
            "test",
            [],
            [],
            "uca-matrix",
            Path("/"),
            diagram_entities={"ucas": []},
        )


def test_inject_includes_noop() -> None:
    body = uca_module.renderer.inject_includes("@startuml\n@enduml", Path("/fake"))
    assert body == "@startuml\n@enduml"


def test_the_renderer_does_not_claim_to_discover_model_references() -> None:
    """This notation's diagram-owned data names no model artifact, and it says so by *not*
    implementing the capability.

    It used to be a required method returning an empty result — twelve of thirteen renderers had one,
    seven of them identical. `collect_references` is `ModelReferencingDiagramRenderer` now, and the
    single caller asks with `isinstance`, so "nothing to discover" is the absence of an implementation
    rather than four lines that delete their arguments."""
    from src.domain.ontology_representation.ontology_protocol import (
        ModelReferencingDiagramRenderer,
    )

    assert not isinstance(uca_module.renderer, ModelReferencingDiagramRenderer)
