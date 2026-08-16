"""arc42 as a shipped document type — and as the test of whether the term vocabulary is enough.

The widened `required_connections` / `suggested_connections` vocabulary was designed with this
template in mind: arc42's sections ask for a *diagram* of a type (§3 a system context, §7 a
deployment view) and a *document* of a type (§9 an ADR), which the entity-only pair could not say.
If a section here needed a field of its own, the vocabulary would be under-designed — so the first
test below is that every term arc42 declares resolves against the catalogs, with nothing invented.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.application.artifacts.document_schema import DocumentSchema, normalize_document_schema
from src.application.artifacts.reference_terms import (
    ReferenceTermVocabulary,
    TermStatus,
    parse_reference_term,
)
from src.domain.repository.repo_default_arc42 import ARC42_ATTRIBUTION
from src.domain.repository.repo_default_schemata import BASE_DOCUMENT_SCHEMAS

#: The twelve, in arc42's own order. Pinned because the order is the template — a section moved or
#: renamed is a different document, and every existing arc42 document would fail E154 on it.
ARC42_SECTIONS = (
    "Introduction and Goals",
    "Architecture Constraints",
    "Context and Scope",
    "Solution Strategy",
    "Building Block View",
    "Runtime View",
    "Deployment View",
    "Cross-cutting Concepts",
    "Architecture Decisions",
    "Quality Requirements",
    "Risks and Technical Debt",
    "Glossary",
)


@lru_cache(maxsize=1)
def _vocabulary() -> ReferenceTermVocabulary:
    """Built over the *complete* vocabulary and a repository holding the shipped document types.

    Complete rather than active: whether the assurance modules are registered depends on the host,
    and a shipped template must not be judged against one deployment's module set.
    """
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs

    catalogs = build_runtime_catalogs(build_module_registry(complete_vocabulary=True))
    return ReferenceTermVocabulary(
        ontology=catalogs.ontology,
        document_labels={doc_type: doc_type for doc_type in BASE_DOCUMENT_SCHEMAS},
        diagram_labels={
            name: module.ui_config.label
            for name, module in catalogs.diagram_types.all_diagram_types().items()
        },
    )


@pytest.fixture(scope="module")
def arc42() -> DocumentSchema:
    return normalize_document_schema("arc42", BASE_DOCUMENT_SCHEMAS["arc42"])


def _all_terms(schema: DocumentSchema) -> list[tuple[str, str]]:
    """Every term the type declares, with where it is declared."""
    terms = [(term, "the document") for term in schema.required_connections + schema.suggested_connections]
    for section in schema.sections:
        terms += [
            (term, f"section '{section.name}'")
            for term in section.required_connections + section.suggested_connections
        ]
    return terms


# ── the vocabulary is expressive enough ──────────────────────────────────────


def test_every_term_arc42_declares_resolves(arc42: DocumentSchema) -> None:
    vocabulary = _vocabulary()

    unresolved = [
        (where, term, vocabulary.status(term).value)
        for term, where in _all_terms(arc42)
        if vocabulary.status(term) is not TermStatus.KNOWN
    ]

    assert unresolved == []


def test_arc42_needs_all_three_vocabularies(arc42: DocumentSchema) -> None:
    """The point of the widening: a section that could only name entity types could not say what
    §3, §7 and §9 are about."""
    kinds = {parse_reference_term(term).kind for term, _ in _all_terms(arc42)}

    assert kinds == {"entity", "document", "diagram"}


def test_it_asks_for_the_c4_types_by_name(arc42: DocumentSchema) -> None:
    by_name = {section.name: section for section in arc42.sections}

    assert "diagram:c4-system-context" in by_name["Context and Scope"].suggested_connections
    assert "diagram:c4-deployment" in by_name["Deployment View"].suggested_connections


# ── the template itself ──────────────────────────────────────────────────────


def test_the_twelve_sections_in_order(arc42: DocumentSchema) -> None:
    assert arc42.required_sections == ARC42_SECTIONS


def test_every_section_says_what_goes_in_it(arc42: DocumentSchema) -> None:
    """A template that pre-writes its own answers is worse than an empty one; a one-line hint per
    section is the whole of what is shipped."""
    for section in arc42.sections:
        assert section.template, f"{section.name} has no hint"
        assert section.template.endswith("\n")
        assert len(section.template.splitlines()) == 1, f"{section.name} pre-writes more than a hint"


def test_only_the_two_unambiguous_sections_require_anything(arc42: DocumentSchema) -> None:
    """An arc42 skeleton must be writable on the day it is created. Decisions belong in §9 and
    quality requirements in §10 — everywhere else the template invites rather than refuses."""
    requiring = {
        section.name: section.required_connections
        for section in arc42.sections
        if section.required_connections
    }

    assert requiring == {
        "Architecture Decisions": ("doc:adr",),
        "Quality Requirements": ("requirement",),
    }
    assert arc42.required_connections == ()


def test_the_id_prefix_does_not_collide_with_a_diagram_type_s(arc42: DocumentSchema) -> None:
    """`ARC` already prefixes ArchiMate diagram ids, so an arc42 document may not take it."""
    from src.application.modeling.artifact_write import prefix_for_diagram_type

    abbreviation = arc42.data["abbreviation"]
    taken = {prefix_for_diagram_type(name) for name in ("archimate-layered", "c4-container", "sequence")}

    assert abbreviation not in taken
    assert abbreviation.isalpha() and abbreviation.isupper() and 2 <= len(abbreviation) <= 6


# ── attribution ──────────────────────────────────────────────────────────────


def test_the_type_carries_its_attribution(arc42: DocumentSchema) -> None:
    """CC BY-SA asks for attribution wherever the work is conveyed, and the create form shows this
    one — an attribution that lives only in a notices file is not seen by whoever writes from the
    template."""
    assert arc42.data["attribution"] == ARC42_ATTRIBUTION
    assert "arc42" in ARC42_ATTRIBUTION
    assert "CC BY-SA 4.0" in ARC42_ATTRIBUTION


def test_the_shipped_content_inventory_names_it() -> None:
    """`THIRD-PARTY-NOTICES.md` is generated from `licenses/`, so a hand-written section there
    would be overwritten; the inventory is where a shipped-content entry has to live."""
    import json

    from tests.support.source_paths import REPO_ROOT

    inventory = json.loads((REPO_ROOT / "licenses" / "content.json").read_text(encoding="utf-8"))
    names = [component["name"] for component in inventory["components"]]

    assert any("arc42" in name for name in names)
    assert inventory["count"] == len(inventory["components"])


def test_the_shipped_schema_matches_this_repository_s_own() -> None:
    """The repository that demonstrates the product carries the type it ships."""
    import json

    from tests.support.source_paths import REPO_ROOT

    local = json.loads(
        (
            REPO_ROOT
            / "engagements/ENG-ARCH-REPO/architecture-repository/.arch-repo/documents/arc42.json"
        ).read_text(encoding="utf-8")
    )

    assert local == BASE_DOCUMENT_SCHEMAS["arc42"]


def test_the_subdirectory_is_a_plain_relative_name() -> None:
    from src.application.artifacts.document_schema import get_document_subdirectory

    assert get_document_subdirectory(BASE_DOCUMENT_SCHEMAS["arc42"], "arc42") == "arc42"


def test_it_is_reachable_as_a_path_under_the_docs_root() -> None:
    assert not Path(BASE_DOCUMENT_SCHEMAS["arc42"]["subdirectory"]).is_absolute()
