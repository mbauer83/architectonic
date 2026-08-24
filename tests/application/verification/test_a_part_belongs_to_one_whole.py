"""E340: two wholes cannot compose one part, because the ontology says they cannot.

ArchiMate 4 defines composition by exclusivity and states it in the ontology: `create_when` admits
one when the target is an integral part of the source "and of that whole alone … no second whole may
claim it"; `never_create_when` sends the shared case to aggregation. Nothing enforced it, so a model
could assert that one part constitutes two wholes and every pass answered zero errors and zero
warnings.

Stated over the declared property rather than over `archimate-composition`: the rule reads
`exclusive_target`, and aggregation — same `relationship_kind`, no exclusivity — must stay unreported
however many wholes share a part, because that is what aggregation is for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier

_ENTITY = """---
artifact-id: {aid}
artifact-type: {atype}
name: {name}
version: 0.1.0
status: draft
---

## Content
An element.
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entity(repo: Path, aid: str, name: str, *, atype: str = "process") -> None:
    _write(
        repo / "model" / "behaviour" / atype / f"{aid}.md",
        _ENTITY.format(aid=aid, atype=atype, name=name),
    )


def _outgoing(repo: Path, source: str, edges: list[tuple[str, str]]) -> None:
    sections = "".join(f"### {conn_type} → {target}\n\nA relation.\n\n" for conn_type, target in edges)
    _write(
        repo / "model" / "behaviour" / "process" / f"{source}.outgoing.md",
        f"---\nsource-entity: {source}\nversion: 0.1.0\nstatus: draft\n---\n\n{sections}",
    )


_W1 = "PRC@1780000001.aaaaaa.whole-one"
_W2 = "PRC@1780000002.aaaaaa.whole-two"
_PART = "FNC@1780000003.aaaaaa.the-part"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _entity(root, _W1, "Whole One")
    _entity(root, _W2, "Whole Two")
    _entity(root, _PART, "The Part", atype="function")
    return root


def _errors(repo: Path, code: str = "E340") -> list[str]:
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs
    from src.infrastructure.artifact_index import shared_artifact_index

    index = shared_artifact_index(repo)
    index.refresh()
    verifier = ArtifactVerifier(
        ArtifactRegistry(index),
        check_puml_syntax=False,
        catalogs=build_runtime_catalogs(build_module_registry()),
    )
    return [
        issue.message
        for result in verifier.verify_all(repo)
        for issue in result.issues
        if issue.code == code
    ]


def test_two_wholes_composing_one_part_is_an_error(repo: Path) -> None:
    """The reproduction from the report, in four items."""
    _outgoing(repo, _W1, [("archimate-composition", _PART)])
    _outgoing(repo, _W2, [("archimate-composition", _PART)])

    messages = _errors(repo)

    assert len(messages) == 1, messages
    assert _PART in messages[0]
    assert _W1 in messages[0] and _W2 in messages[0], "both wholes are named, so the fix is obvious"
    assert "archimate-composition" in messages[0]


def test_one_whole_composing_a_part_is_fine(repo: Path) -> None:
    _outgoing(repo, _W1, [("archimate-composition", _PART)])

    assert _errors(repo) == []


def test_two_wholes_aggregating_one_part_is_fine(repo: Path) -> None:
    """Aggregation is what the shared case is *for*, and carries the same `relationship_kind`. A rule
    that keyed on containment rather than on the declared exclusivity would fail here."""
    _outgoing(repo, _W1, [("archimate-aggregation", _PART)])
    _outgoing(repo, _W2, [("archimate-aggregation", _PART)])

    assert _errors(repo) == []


def test_a_third_whole_is_named_in_the_one_finding(repo: Path) -> None:
    """One finding per part, naming every whole that claims it — the thing to fix is the part's
    membership, and a finding per claim would make the reader count them.

    (A single file declaring the same composition twice cannot reach this rule: two identical
    declarations mint one connection id, and the index refuses the duplicate first.)"""
    third = "PRC@1780000004.aaaaaa.whole-three"
    _entity(repo, third, "Whole Three")
    for whole in (_W1, _W2, third):
        _outgoing(repo, whole, [("archimate-composition", _PART)])

    messages = _errors(repo)

    assert len(messages) == 1, messages
    assert "claimed by 3 sources" in messages[0]
    assert all(whole in messages[0] for whole in (_W1, _W2, third))


def test_a_relation_that_claims_nothing_exclusively_is_never_reported(repo: Path) -> None:
    """Every other relation in the ontology permits many sources per target."""
    _outgoing(repo, _W1, [("archimate-assignment", _PART)])
    _outgoing(repo, _W2, [("archimate-assignment", _PART)])

    assert _errors(repo) == []


def test_the_rule_reaches_a_project_layout_as_well_as_the_legacy_root(tmp_path: Path) -> None:
    """Model content lives under `projects/<slug>/model/` as well as `model/`, and the wholes may sit
    in different projects — where a rule reading one root would see one claim each."""
    root = tmp_path / "engagements" / "ENG-P" / "architecture-repository"
    for slug, whole in (("alpha", _W1), ("beta", _W2)):
        _write(
            root / "projects" / slug / "model" / "behaviour" / "process" / f"{whole}.md",
            _ENTITY.format(aid=whole, atype="process", name=whole),
        )
        _write(
            root / "projects" / slug / "model" / "behaviour" / "process" / f"{whole}.outgoing.md",
            f"---\nsource-entity: {whole}\nversion: 0.1.0\nstatus: draft\n---\n\n"
            f"### archimate-composition → {_PART}\n\nA relation.\n",
        )
    _write(
        root / "projects" / "alpha" / "model" / "behaviour" / "function" / f"{_PART}.md",
        _ENTITY.format(aid=_PART, atype="function", name="The Part"),
    )

    messages = _errors(root)

    assert len(messages) == 1, messages
    assert _W1 in messages[0] and _W2 in messages[0]
