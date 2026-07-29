"""WU-0.3: normalize_diagram_entity_identities allocates and rewrites workspace IDs."""

from __future__ import annotations

import re

from src.application.identifier_allocator import DefaultIdentifierAllocator
from src.infrastructure.app_bootstrap import build_module_catalog, build_module_registry
from src.infrastructure.write.artifact_write.diagram_entity_identity import (
    normalize_diagram_entity_identities,
)

_WORKSPACE_ID_RE = re.compile(r"^[A-Z]+@[0-9]+\.[A-Za-z0-9_-]+\..+$")
_CLF_RE = re.compile(r"^CLF@[0-9]+\.[A-Za-z0-9_-]+\..+$")


def _catalog():
    return build_module_catalog(build_module_registry(complete_vocabulary=True))


def _allocator():
    return DefaultIdentifierAllocator()


def test_allocates_missing_classifier_id():
    entities = {"classifier": [{"id": "", "label": "Customer", "classifier_kind": "class"}]}
    result, _, _ = normalize_diagram_entity_identities(
        "datatype", entities, [], [],
        module_catalog=_catalog(), allocator=_allocator(),
    )
    ids = [item["id"] for item in result["classifier"]]
    assert len(ids) == 1
    assert _CLF_RE.match(ids[0]), f"Expected CLF@ id, got {ids[0]!r}"


def test_existing_valid_id_preserved():
    valid_id = "CLF@1000000000.AbCdEf.order"
    entities = {"classifier": [{"id": valid_id, "label": "Order", "classifier_kind": "class"}]}
    result, _, _ = normalize_diagram_entity_identities(
        "datatype", entities, [], [],
        module_catalog=_catalog(), allocator=_allocator(),
    )
    assert result["classifier"][0]["id"] == valid_id


def test_temp_id_rewrites_connection_endpoints():
    temp_id = "temp-1"
    entities = {"classifier": [{"id": temp_id, "label": "Foo", "classifier_kind": "class"}]}
    connections = [{"source": temp_id, "target": "some-other", "conn_type": "dt-association"}]
    _, new_conns, _ = normalize_diagram_entity_identities(
        "datatype", entities, connections, [],
        module_catalog=_catalog(), allocator=_allocator(),
    )
    assert new_conns[0]["source"] != temp_id
    assert _CLF_RE.match(new_conns[0]["source"])


def test_temp_id_rewrites_binding_references():
    temp_id = "temp-2"
    entities = {"classifier": [{"id": temp_id, "label": "Bar", "classifier_kind": "class"}]}
    bindings = [{"entity_id": temp_id, "binding_kind": "represents"}]
    _, _, new_bindings = normalize_diagram_entity_identities(
        "datatype", entities, [], bindings,
        module_catalog=_catalog(), allocator=_allocator(),
    )
    assert new_bindings[0]["entity_id"] != temp_id
    assert _CLF_RE.match(new_bindings[0]["entity_id"])


def test_temp_id_rewrites_classifier_type_reference():
    """Self-references (classifier attr type pointing to another classifier) are rewritten."""
    temp_id = "temp-3"
    entities = {
        "classifier": [
            {"id": temp_id, "label": "Base", "classifier_kind": "class"},
            {
                "id": "CLF@9000000000.AbCdEf.child",
                "label": "Child",
                "classifier_kind": "class",
                "attributes": [{"name": "base", "type": {"kind": "classifier", "id": temp_id}}],
            },
        ]
    }
    result, _, _ = normalize_diagram_entity_identities(
        "datatype", entities, [], [],
        module_catalog=_catalog(), allocator=_allocator(),
    )
    new_id = result["classifier"][0]["id"]
    assert _CLF_RE.match(new_id)
    attr_ref = result["classifier"][1]["attributes"][0]["type"]
    assert attr_ref["id"] == new_id


def test_non_workspace_entity_type_untouched():
    """Entity types without workspace identity are passed through unchanged."""
    entities = {"some-other-type": [{"id": "temp", "label": "X"}]}
    result, _, _ = normalize_diagram_entity_identities(
        "datatype", entities, [], [],
        module_catalog=_catalog(), allocator=_allocator(),
    )
    assert result["some-other-type"][0]["id"] == "temp"


def test_unknown_diagram_type_returns_unchanged():
    entities = {"classifier": [{"id": "", "label": "X", "classifier_kind": "class"}]}
    result, conns, binds = normalize_diagram_entity_identities(
        "no-such-type", entities, [], [],
        module_catalog=_catalog(), allocator=_allocator(),
    )
    assert result is entities


def test_no_allocation_when_all_ids_valid():
    valid_id = "CLF@1000000001.AbCdEf.item"
    entities = {"classifier": [{"id": valid_id, "label": "Item", "classifier_kind": "class"}]}
    result, conns, binds = normalize_diagram_entity_identities(
        "datatype", entities, [], [],
        module_catalog=_catalog(), allocator=_allocator(),
    )
    assert result is entities
