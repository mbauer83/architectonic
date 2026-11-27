"""A341: an ordered sequence with two or more composed parts and no order between them is advice.

Every test here runs `verify_all` over a verifier built the way the product builds one — an
`ArtifactRegistry` over the index and no committed repository — so the repository-level rule meets
the point-lookup-only candidate repository whose `list_*` answer `[]`. That is the trap B58 named: a
rule enumerating content through it is silent in the product and green in a test that hands it a
real store.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.domain.verification_findings import Issue

_ENTITY = """---
artifact-id: {aid}
artifact-type: {atype}
name: {name}
version: 0.1.0
status: {status}
last-updated: '2026-11-27'
{extra}---

## Content
An element.
"""

_PROCESS = "PRC@1780000001.aaaaaa.handle-order"
_A = "PRC@1780000002.aaaaaa.take-order"
_B = "PRC@1780000003.aaaaaa.ship-order"
_C = "FNC@1780000004.aaaaaa.bill-order"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity(repo: Path, aid: str, *, atype: str = "process", status: str = "draft", extra: str = "") -> None:
    _write(
        repo / "model" / "common" / atype / f"{aid}.md",
        _ENTITY.format(aid=aid, atype=atype, name=aid.rsplit(".", 1)[-1], status=status, extra=extra),
    )


def _outgoing(repo: Path, source: str, edges: list[tuple[str, str]], *, atype: str = "process") -> None:
    sections = "".join(f"### {conn_type} → {target}\n\nA relation.\n\n" for conn_type, target in edges)
    _write(
        repo / "model" / "common" / atype / f"{source}.outgoing.md",
        f"---\nsource-entity: {source}\nversion: 0.1.0\nstatus: draft\nlast-updated: '2026-11-27'\n---\n\n{sections}",
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _entity(root, _A)
    _entity(root, _B)
    _entity(root, _C, atype="function")
    return root


def _advice(repo: Path) -> list[Issue]:
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
    from src.infrastructure.artifact_index import shared_artifact_index

    index = shared_artifact_index(repo)
    index.refresh()
    verifier = ArtifactVerifier(
        ArtifactRegistry(index), check_puml_syntax=False, catalogs=build_runtime_catalogs(build_module_registry())
    )
    return [issue for result in verifier.verify_all(repo) for issue in result.issues if issue.code == "A341"]


def _compose(repo: Path, *parts: str) -> None:
    _outgoing(repo, _PROCESS, [("archimate-composition", part) for part in parts])


@pytest.mark.verifies("REQ@1795776616.gmLsdPo")
def test_a_process_with_two_unordered_parts_yields_one_advice_naming_them(repo: Path) -> None:
    _entity(repo, _PROCESS)
    _compose(repo, _A, _B)

    advice = _advice(repo)

    assert len(advice) == 1, advice
    (finding,) = advice
    assert finding.severity == "advice"
    assert _A in finding.message and _B in finding.message
    assert finding.details == {"artifact_id": _PROCESS, "status": "draft", "parts": sorted([_A, _B])}
    assert finding.location.endswith(f"{_PROCESS}.md")


def test_advice_never_makes_a_file_invalid(repo: Path) -> None:
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
    from src.infrastructure.artifact_index import shared_artifact_index

    _entity(repo, _PROCESS)
    _compose(repo, _A, _B)
    index = shared_artifact_index(repo)
    index.refresh()
    verifier = ArtifactVerifier(
        ArtifactRegistry(index), check_puml_syntax=False, catalogs=build_runtime_catalogs(build_module_registry())
    )
    results = verifier.verify_all(repo)
    carrying = [r for r in results if r.advice]
    assert carrying and all(r.valid for r in carrying)


@pytest.mark.parametrize("order", ["archimate-triggering", "archimate-flow"])
def test_one_dynamic_relation_between_the_parts_quiets_it(repo: Path, order: str) -> None:
    _entity(repo, _PROCESS)
    _compose(repo, _A, _B, _C)
    _outgoing(repo, _A, [(order, _B)])

    assert _advice(repo) == []


_J1 = "JNA@1780000011.aaaaaa.both"
_J2 = "JNO@1780000012.aaaaaa.either"


@pytest.mark.parametrize("order", ["archimate-triggering", "archimate-flow"])
def test_order_through_one_junction_quiets_it(repo: Path, order: str) -> None:
    """part → junction → part is ordinary ArchiMate: the junction carries one relation on."""
    _entity(repo, _PROCESS)
    _entity(repo, _J1, atype="and-junction")
    _compose(repo, _A, _B)
    _outgoing(repo, _A, [(order, _J1)])
    _outgoing(repo, _J1, [(order, _B)], atype="and-junction")

    assert _advice(repo) == []


def test_order_through_chained_junctions_quiets_it(repo: Path) -> None:
    _entity(repo, _PROCESS)
    _entity(repo, _J1, atype="and-junction")
    _entity(repo, _J2, atype="or-junction")
    _compose(repo, _A, _B)
    _outgoing(repo, _A, [("archimate-triggering", _J1)])
    _outgoing(repo, _J1, [("archimate-triggering", _J2)], atype="and-junction")
    _outgoing(repo, _J2, [("archimate-triggering", _B)], atype="or-junction")

    assert _advice(repo) == []


def test_a_junction_whose_legs_do_not_express_order_does_not_quiet_it(repo: Path) -> None:
    _entity(repo, _PROCESS)
    _entity(repo, _J1, atype="and-junction")
    _compose(repo, _A, _B)
    _outgoing(repo, _A, [("archimate-serving", _J1)])
    _outgoing(repo, _J1, [("archimate-serving", _B)], atype="and-junction")

    assert len(_advice(repo)) == 1


def test_order_through_another_step_quiets_it(repo: Path) -> None:
    """A chain of triggering derives triggering between its ends, so a step between the parts orders them."""
    _entity(repo, _PROCESS)
    _compose(repo, _A, _C)
    _outgoing(repo, _A, [("archimate-triggering", _B)])
    _outgoing(repo, _B, [("archimate-triggering", _C)])

    assert _advice(repo) == []


def test_a_chain_broken_by_a_relation_that_does_not_express_order_does_not_quiet_it(repo: Path) -> None:
    _entity(repo, _PROCESS)
    _compose(repo, _A, _C)
    _outgoing(repo, _A, [("archimate-triggering", _B)])
    _outgoing(repo, _B, [("archimate-serving", _C)])

    assert len(_advice(repo)) == 1


def test_a_relation_that_does_not_express_order_does_not_quiet_it(repo: Path) -> None:
    _entity(repo, _PROCESS)
    _compose(repo, _A, _B)
    _outgoing(repo, _A, [("archimate-serving", _B)])

    assert len(_advice(repo)) == 1


def test_one_part_is_not_advice(repo: Path) -> None:
    _entity(repo, _PROCESS)
    _compose(repo, _A)

    assert _advice(repo) == []


def test_a_type_that_is_not_a_sequence_is_never_advised(repo: Path) -> None:
    whole = "FNC@1780000009.aaaaaa.ordering"
    _entity(repo, whole, atype="function")
    _outgoing(repo, whole, [("archimate-composition", _A), ("archimate-composition", _B)], atype="function")

    assert _advice(repo) == []


def test_aggregated_parts_are_not_composed_parts(repo: Path) -> None:
    _entity(repo, _PROCESS)
    _outgoing(repo, _PROCESS, [("archimate-aggregation", _A), ("archimate-aggregation", _B)])

    assert _advice(repo) == []


@pytest.mark.parametrize("status", ["draft", "active", "deprecated"])
def test_an_acknowledged_advice_is_quiet_at_every_status(repo: Path, status: str) -> None:
    _entity(
        repo, _PROCESS, status=status,
        extra="accepted-advice:\n- code: A341\n  reason: A checklist; the steps run in any order.\n",
    )
    _compose(repo, _A, _B)

    assert _advice(repo) == []


def test_acknowledging_another_code_does_not_quiet_this_one(repo: Path) -> None:
    _entity(repo, _PROCESS, extra="accepted-advice:\n- code: A999\n  reason: something else\n")
    _compose(repo, _A, _B)

    assert len(_advice(repo)) == 1


def test_the_status_recorded_is_the_elements(repo: Path) -> None:
    _entity(repo, _PROCESS, status="active")
    _compose(repo, _A, _B)

    (finding,) = _advice(repo)
    assert finding.details is not None and finding.details["status"] == "active"


def test_the_rule_names_no_ontology_type() -> None:
    """The verifier reads the ontology's flag and roles; it never spells a type."""
    from src.application.verification import _ordered_sequence_rule
    from src.domain.relationships import ordered_sequences

    for module in (_ordered_sequence_rule, ordered_sequences):
        source = Path(module.__file__).read_text(encoding="utf-8")
        code = source.split('"""', 2)[2]
        for name in ("archimate", "'process'", '"process"', "triggering", "'flow'", '"flow"', "junction'", 'junction"'):
            assert name not in code, f"{module.__name__} names {name}"
