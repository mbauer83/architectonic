"""Tests for the W127 junction-multiplicity verifier rule: a read-time complement
to the write-time hard block in `connection.py::add_connection`, catching persisted data
that predates that guard or entered through the edit path (which doesn't enforce it).

`_entity_type` is monkeypatched directly (not a loose `MagicMock`) so these tests exercise
real registry I/O for nothing they don't need. An unconfigured mock standing in for a real
filesystem-backed lookup answers every query plausibly and asserts nothing — the failure mode
that once let a whole upgrade framework pass its tests without touching a repository.
"""

from __future__ import annotations

from pathlib import Path

from src.application.verification import _verifier_rules_semantic as sem
from src.application.verification._verifier_rules_semantic import check_connection_semantics
from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.repository.connection_declaration import ConnectionDeclaration


class _FakeRegistry:
    """The graph surface the junction rules need, answering "no other legs".

    W127 judges one connection end on its own, but the admissibility rules (E128/E129) ask the
    junction what else it joins — so a registry stand-in has to answer that question. `object()`
    never could; it only got away with it while no rule here looked past the declaration.
    """

    def find_connections_for(self, entity_id: str, *, direction: str = "any", conn_type: str | None = None) -> list:
        return []


class _FakeOntologyCatalog:
    def __init__(self, junction_types: frozenset[str]) -> None:
        self._junction_types = junction_types

    def entity_types_with_class(self, element_class: str) -> frozenset[str]:
        return self._junction_types if element_class == "junction" else frozenset()


def _patch_entity_types(monkeypatch, types: dict[str, str]) -> None:
    monkeypatch.setattr(sem, "_entity_type", lambda _registry, entity_id: types.get(entity_id))


def _result() -> VerificationResult:
    return VerificationResult(path=Path("x.outgoing.md"), file_type="connection")


def _decl(conn_type: str, target_id: str, src_mult: str = "", tgt_mult: str = "") -> ConnectionDeclaration:
    return ConnectionDeclaration(
        conn_type=conn_type, target_id=target_id, src_multiplicity=src_mult, tgt_multiplicity=tgt_mult
    )


def test_w127_fires_when_source_is_a_junction_with_multiplicity(monkeypatch) -> None:
    _patch_entity_types(monkeypatch, {"SRC@1.abc.j": "junction", "TGT@1.abc.t": "requirement"})
    result = _result()

    check_connection_semantics(
        "SRC@1.abc.j",
        [_decl("archimate-association", "TGT@1.abc.t", "1", "")],
        registry=_FakeRegistry(),
        result=result,
        loc="loc",
        ontology_catalog=_FakeOntologyCatalog(junction_types=frozenset({"junction"})),
    )

    (issue,) = result.issues
    assert issue.code == "W127"
    assert "Source multiplicity" in issue.message
    assert "SRC@1.abc.j" in issue.message


def test_w127_fires_when_target_is_a_junction_with_multiplicity(monkeypatch) -> None:
    _patch_entity_types(monkeypatch, {"SRC@1.abc.s": "requirement", "TGT@1.abc.j": "junction"})
    result = _result()

    check_connection_semantics(
        "SRC@1.abc.s",
        [_decl("archimate-association", "TGT@1.abc.j", "", "1")],
        registry=_FakeRegistry(),
        result=result,
        loc="loc",
        ontology_catalog=_FakeOntologyCatalog(junction_types=frozenset({"junction"})),
    )

    (issue,) = result.issues
    assert issue.code == "W127"
    assert "Target multiplicity" in issue.message


def test_no_w127_when_multiplicity_absent_even_on_a_junction(monkeypatch) -> None:
    _patch_entity_types(monkeypatch, {"SRC@1.abc.j": "junction", "TGT@1.abc.t": "requirement"})
    result = _result()

    check_connection_semantics(
        "SRC@1.abc.j",
        [_decl("archimate-association", "TGT@1.abc.t", "", "")],
        registry=_FakeRegistry(),
        result=result,
        loc="loc",
        ontology_catalog=_FakeOntologyCatalog(junction_types=frozenset({"junction"})),
    )

    assert result.issues == []


def test_no_w127_when_multiplicity_set_but_not_a_junction(monkeypatch) -> None:
    _patch_entity_types(monkeypatch, {"SRC@1.abc.s": "requirement", "TGT@1.abc.t": "requirement"})
    result = _result()

    check_connection_semantics(
        "SRC@1.abc.s",
        [_decl("archimate-association", "TGT@1.abc.t", "1", "1")],
        registry=_FakeRegistry(),
        result=result,
        loc="loc",
        ontology_catalog=_FakeOntologyCatalog(junction_types=frozenset({"junction"})),
    )

    assert result.issues == []


def test_no_w127_when_ontology_catalog_not_injected(monkeypatch) -> None:
    _patch_entity_types(monkeypatch, {"SRC@1.abc.j": "junction", "TGT@1.abc.t": "requirement"})
    result = _result()

    check_connection_semantics(
        "SRC@1.abc.j",
        [_decl("archimate-association", "TGT@1.abc.t", "1", "")],
        registry=_FakeRegistry(),
        result=result,
        loc="loc",
        ontology_catalog=None,
    )

    assert result.issues == []
