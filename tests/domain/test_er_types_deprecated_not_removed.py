"""Guard: the deprecated er-* connection types must stay loadable.

They are superseded by the datatype diagram's diagram-local dt-* types, but a repository
authored before that change still holds er-* connection files. Dropping the types would
fail verification on those files rather than migrate them, so removal waits until the
migration has run.
"""

from __future__ import annotations

from src.ontologies.archimate_4 import module as archimate_module


def test_er_types_still_present() -> None:
    ct = archimate_module.connection_types
    assert "er-one-to-many" in ct, "er-one-to-many removed prematurely"
    assert "er-many-to-many" in ct, "er-many-to-many removed prematurely"
    assert "er-one-to-one" in ct, "er-one-to-one removed prematurely"


def test_er_types_have_diagram_conn_lang() -> None:
    ct = archimate_module.connection_types
    for name in ("er-one-to-many", "er-many-to-many", "er-one-to-one"):
        assert ct[name].conn_lang == "er", f"{name} has unexpected conn_lang"
