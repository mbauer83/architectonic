"""find_file_by_id resolves every standalone artifact kind, group subdirectories included.

Regression guard: the resolver previously consulted only the entity map, so diagrams and
documents in a group collection (a subdirectory of the catalog) could not be resolved by
id — the write/refresh layer then fell back to a flat path and 404'd. It must resolve
entities, diagrams, and documents at whatever path the index recorded.

Also covers the short (rename-stable) id form: find_file_by_id previously did an exact-key
lookup only, so a short-form id (no trailing `.slug`) always reported "not found" for
diagrams/documents/entities alike — artifact_edit_diagram, delete_entity, etc. all rejected
short ids even though several MCP tools' own docstrings advertise short-id support. Fixed by
canonicalizing through `_MemStore.canonical_id` (already used by `read_artifact`/
`summarize_artifact`) before the exact-key lookups.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.infrastructure.artifact_index._mem_store import _MemStore
from src.infrastructure.artifact_index._rwlock import _RWLock
from src.infrastructure.artifact_index._scope_registry import _ScopeRegistry


def _registry(mem: _MemStore) -> _ScopeRegistry:
    return _ScopeRegistry(mem, _RWLock(), lambda: None, lambda _p: "engagement")


def test_resolves_entity_diagram_and_document_in_subdirectories() -> None:
    # find_file_by_id reads only `.path`; lightweight stand-ins keep the test focused.
    mem = _MemStore()
    ent_path = Path("/repo/projects/grp/model/motivation/STK@1.a.s.md")
    diag_path = Path("/repo/diagram-catalog/diagrams/meta-ontology/DATATY@1.b.d.puml")
    doc_path = Path("/repo/document-catalog/documents/grp/DOC@1.c.x.md")
    mem.entities["STK@1.a.s"] = SimpleNamespace(path=ent_path)  # type: ignore[assignment]
    mem.diagrams["DATATY@1.b.d"] = SimpleNamespace(path=diag_path)  # type: ignore[assignment]
    mem.documents["DOC@1.c.x"] = SimpleNamespace(path=doc_path)  # type: ignore[assignment]
    reg = _registry(mem)

    assert reg.find_file_by_id("STK@1.a.s") == ent_path
    assert reg.find_file_by_id("DATATY@1.b.d") == diag_path
    assert reg.find_file_by_id("DOC@1.c.x") == doc_path
    assert reg.find_file_by_id("MISSING@9.z.z") is None


def test_resolves_short_form_id_for_each_kind() -> None:
    mem = _MemStore()
    ent_path = Path("/repo/model/motivation/STK@1.abcde.stakeholder-name.md")
    diag_path = Path("/repo/diagram-catalog/diagrams/grp/MAT@2.fghij.some-matrix.md")
    doc_path = Path("/repo/document-catalog/documents/DOC@3.klmno.some-doc.md")
    mem.entities["STK@1.abcde.stakeholder-name"] = SimpleNamespace(path=ent_path)  # type: ignore[assignment]
    mem.diagrams["MAT@2.fghij.some-matrix"] = SimpleNamespace(path=diag_path)  # type: ignore[assignment]
    mem.documents["DOC@3.klmno.some-doc"] = SimpleNamespace(path=doc_path)  # type: ignore[assignment]
    reg = _registry(mem)

    # Full id (exact key) still resolves — the fast, common path is untouched.
    assert reg.find_file_by_id("STK@1.abcde.stakeholder-name") == ent_path
    # Short id (no trailing .slug) now also resolves for every kind.
    assert reg.find_file_by_id("STK@1.abcde") == ent_path
    assert reg.find_file_by_id("MAT@2.fghij") == diag_path
    assert reg.find_file_by_id("DOC@3.klmno") == doc_path


def test_ambiguous_short_id_across_two_full_ids_fails_safe_to_none() -> None:
    """Two distinct full ids sharing one short id must not silently pick either."""
    mem = _MemStore()
    mem.diagrams["MAT@2.fghij.old-name"] = SimpleNamespace(path=Path("/repo/a.md"))  # type: ignore[assignment]
    mem.diagrams["MAT@2.fghij.new-name"] = SimpleNamespace(path=Path("/repo/b.md"))  # type: ignore[assignment]
    reg = _registry(mem)

    assert reg.find_file_by_id("MAT@2.fghij") is None
