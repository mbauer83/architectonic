"""Regression: diagram-owned connection types must reach the module registry.

Sequence and activity diagrams declare connection types (``seq-from``, ``step-flow``, …) in
their ``ontology.yaml``. These must surface through ``own_connection_types`` so that
``ModuleRegistry.all_connection_types()`` — and therefore startup repo-compatibility
validation — recognises them. They previously returned an unpopulated empty dict, so a
freshly started backend aborted with "Unknown connection type 'seq-from'" on any repository
containing a sequence or activity diagram.
"""

from __future__ import annotations

import src.infrastructure.app_bootstrap as app_bootstrap

_SEQUENCE = {"seq-from", "seq-to"}
_ACTIVITY = {"step-flow", "step-else", "step-then", "step-in-lane"}


def test_diagram_owned_connection_types_reach_all_connection_types() -> None:
    registry = app_bootstrap.build_module_registry(complete_vocabulary=True)
    known = {str(t) for t in registry.all_connection_types()}

    assert _SEQUENCE <= known
    assert _ACTIVITY <= known


def test_sequence_and_activity_expose_their_declared_connection_types() -> None:
    registry = app_bootstrap.build_module_registry(complete_vocabulary=True)
    diagram_types = registry.all_diagram_types()

    assert _SEQUENCE <= {str(k) for k in diagram_types["sequence"].own_connection_types}
    assert _ACTIVITY <= {str(k) for k in diagram_types["activity"].own_connection_types}
