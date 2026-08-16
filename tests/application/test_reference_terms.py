"""The one reading of a required-/suggested-reference term, across all three vocabularies.

The prefix is a syntax this project reads, so it has an owner and a row in
`tests/architecture/test_each_syntax_has_one_reader.py`. These are its unit tests; the rules that
consume it are exercised end to end in `tests/tools/test_verifier.py`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

from src.application.artifacts.reference_terms import (
    LinkedArtifactTypes,
    ReferenceTermVocabulary,
    TermStatus,
    parse_reference_term,
)
from src.application.document_links import ResolvedArtifactLink


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    schema_dir = tmp_path / ".arch-repo" / "documents"
    schema_dir.mkdir(parents=True)
    (schema_dir / "adr.json").write_text(
        json.dumps({"name": "Architecture Decision Record"}), encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def vocabulary(repo_root: Path) -> ReferenceTermVocabulary:
    return ReferenceTermVocabulary.for_repository(catalogs=_catalogs(), repo_root=repo_root)


def _link(kind: str, type_name: str) -> ResolvedArtifactLink:
    return ResolvedArtifactLink(
        href="x.md", artifact_id="X@1.AbcDef.x", kind=kind, type_name=type_name, name="X"  # type: ignore[arg-type]
    )


# ── parsing ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("term", "kind", "body"),
    [
        ("requirement", "entity", "requirement"),
        ("@all", "entity", "@all"),
        ("@internal-behavior-element", "entity", "@internal-behavior-element"),
        ("doc:adr", "document", "adr"),
        ("doc:@all", "document", "@all"),
        ("diagram:c4-container", "diagram", "c4-container"),
        ("  diagram: matrix  ", "diagram", "matrix"),
    ],
)
def test_parse_reference_term(term: str, kind: str, body: str) -> None:
    parsed = parse_reference_term(term)
    assert (parsed.kind, parsed.body) == (kind, body)


# ── status ───────────────────────────────────────────────────────────────────


def test_known_terms_across_the_three_vocabularies(vocabulary: ReferenceTermVocabulary) -> None:
    assert vocabulary.status("requirement") is TermStatus.KNOWN
    assert vocabulary.status("@internal-behavior-element") is TermStatus.KNOWN
    assert vocabulary.status("doc:adr") is TermStatus.KNOWN
    assert vocabulary.status("diagram:matrix") is TermStatus.KNOWN


def test_any_is_known_in_every_vocabulary(vocabulary: ReferenceTermVocabulary) -> None:
    assert vocabulary.status("@all") is TermStatus.KNOWN
    assert vocabulary.status("doc:@all") is TermStatus.KNOWN
    assert vocabulary.status("diagram:@all") is TermStatus.KNOWN


def test_an_entity_or_document_type_that_does_not_exist_is_unknown(
    vocabulary: ReferenceTermVocabulary,
) -> None:
    assert vocabulary.status("not-an-entity-type") is TermStatus.UNKNOWN
    assert vocabulary.status("doc:not-a-doc-type") is TermStatus.UNKNOWN


def test_an_unregistered_diagram_type_is_neither_known_nor_unknown(
    vocabulary: ReferenceTermVocabulary,
) -> None:
    """The catalog outlives the registry: a host without the confidential store registers no
    assurance diagram types, and a stored diagram of one is still a diagram of that type."""
    assert vocabulary.status("diagram:not-a-registered-type") is TermStatus.UNREGISTERED


# ── matching ─────────────────────────────────────────────────────────────────


def test_a_term_is_matched_only_within_its_own_vocabulary(
    vocabulary: ReferenceTermVocabulary,
) -> None:
    """The three namespaces do not overlap, and a shared name must not cross between them."""
    linked = LinkedArtifactTypes(document=frozenset({"requirement"}))
    assert not vocabulary.matches("requirement", linked)
    assert vocabulary.matches("doc:requirement", linked)


def test_class_terms_still_expand_through_the_ontology(vocabulary: ReferenceTermVocabulary) -> None:
    assert vocabulary.matches("@internal-behavior-element", LinkedArtifactTypes(entity=frozenset({"function"})))
    assert not vocabulary.matches("@internal-behavior-element", LinkedArtifactTypes(entity=frozenset({"driver"})))


def test_any_matches_whatever_is_present_in_that_vocabulary(
    vocabulary: ReferenceTermVocabulary,
) -> None:
    assert vocabulary.matches("doc:@all", LinkedArtifactTypes(document=frozenset({"standard"})))
    assert not vocabulary.matches("doc:@all", LinkedArtifactTypes(entity=frozenset({"requirement"})))


def test_satisfied_by_answers_for_one_link(vocabulary: ReferenceTermVocabulary) -> None:
    assert vocabulary.satisfied_by("doc:adr", _link("document", "adr"))
    assert not vocabulary.satisfied_by("doc:adr", _link("diagram", "adr"))


def test_from_links_partitions_by_kind() -> None:
    linked = LinkedArtifactTypes.from_links(
        [_link("entity", "requirement"), _link("document", "adr"), _link("diagram", "matrix")]
    )
    assert linked.entity == frozenset({"requirement"})
    assert linked.document == frozenset({"adr"})
    assert linked.diagram == frozenset({"matrix"})


# ── labelling ────────────────────────────────────────────────────────────────


def test_a_label_names_what_an_author_would_go_and_create(
    vocabulary: ReferenceTermVocabulary,
) -> None:
    assert vocabulary.label("doc:adr") == "Architecture Decision Record"
    assert vocabulary.label("@internal-behavior-element") == "internal behavior element"
    assert vocabulary.label("diagram:matrix") == _catalogs().diagram_types.get_diagram_type(
        "matrix"
    ).ui_config.label


def test_an_unregistered_diagram_type_still_labels_readably(
    vocabulary: ReferenceTermVocabulary,
) -> None:
    assert vocabulary.label("diagram:not-a-registered-type") == "not a registered type"


def test_kind_noun_names_the_vocabulary(vocabulary: ReferenceTermVocabulary) -> None:
    assert vocabulary.kind_noun("requirement") == "entity-type"
    assert vocabulary.kind_noun("doc:adr") == "document-type"
    assert vocabulary.kind_noun("diagram:matrix") == "diagram-type"
