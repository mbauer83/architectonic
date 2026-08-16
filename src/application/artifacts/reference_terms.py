"""What a required- or suggested-reference term names, and whether a document's links satisfy it.

A document type — and a section within it — declares the model content a document of that type is
expected to reach. The vocabulary spans three catalogs: entity types and their classes come from the
ontology, document types from this repository's own schemata, and diagram types from the module
registry. The reading of a term lives here once, because the alternative is the kind prefix spelled
in the verifier, again in the promotion closure, again in the placeholder writer and a fourth time
in the GUI — which is how the entity-only pair came to be enumerated by name at thirteen sites.

Diagram types are the one *conditional* vocabulary. A host without the confidential store registers
no assurance module, so ``diagram:bowtie`` is a term this deployment cannot expand while a stored
diagram of that type can still satisfy it. That is a third answer rather than "unknown", and an
unmet requirement in that state is a warning: a shipped template must not become unsatisfiable
because of what the host it runs on happens to register.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.document_links import ArtifactLinkKind, ResolvedArtifactLink

if TYPE_CHECKING:
    from src.application.runtime_catalogs import RuntimeCatalogs
    from src.domain.modules.catalogs import OntologyCatalog

#: A term names one of the three vocabularies a link can resolve to. The same type as the link
#: classification, from the module that owns it — a term kind the classifier cannot produce would be
#: a term nothing could ever satisfy.
ReferenceKind = ArtifactLinkKind

#: The prefix that moves a term out of the default vocabulary. Bare terms stay entity types, so
#: every schema authored before the widening reads unchanged and needs no migration.
DOCUMENT_TERM_PREFIX = "doc:"
DIAGRAM_TERM_PREFIX = "diagram:"

#: "any of this kind", spelled as the entity vocabulary already spells it.
ANY_TERM = "@all"

_PREFIXED_KINDS: tuple[tuple[str, ReferenceKind], ...] = (
    (DOCUMENT_TERM_PREFIX, "document"),
    (DIAGRAM_TERM_PREFIX, "diagram"),
)

#: How each kind names itself in a verification message, so one message template serves all three.
KIND_NOUNS: Mapping[ReferenceKind, str] = {
    "entity": "entity-type",
    "document": "document-type",
    "diagram": "diagram-type",
}

_ANY_LABELS: Mapping[ReferenceKind, str] = {
    "entity": "entity",
    "document": "document",
    "diagram": "diagram",
}


class TermStatus(Enum):
    """Whether a term names something this deployment can expand.

    ``UNREGISTERED`` exists for diagram types alone: the catalog holds types the registry does not
    provide, and refusing a document for naming one would make the answer depend on the host.
    """

    KNOWN = "known"
    UNKNOWN = "unknown"
    UNREGISTERED = "unregistered"


@dataclass(frozen=True)
class ReferenceTerm:
    """One declared term, split into the vocabulary it names and the name within it."""

    kind: ReferenceKind
    body: str

    @property
    def is_any(self) -> bool:
        return self.body == ANY_TERM


def parse_reference_term(term: str) -> ReferenceTerm:
    """Split a declared term into its vocabulary and its name.

    The single reading of the kind prefix. A term with no prefix is an entity term, which is what
    every term was before document and diagram types joined the vocabulary.
    """
    written = term.strip()
    for prefix, kind in _PREFIXED_KINDS:
        if written.startswith(prefix):
            return ReferenceTerm(kind=kind, body=written[len(prefix) :].strip())
    return ReferenceTerm(kind="entity", body=written)


@dataclass(frozen=True)
class LinkedArtifactTypes:
    """The types a span's links resolve to, partitioned by the kind of artifact each turned out to be.

    Partitioned rather than one set of names, because the vocabularies do not share a namespace: a
    document type and an entity type may spell themselves the same way, and an entity term must not
    be satisfied by a document that happens to agree.
    """

    entity: frozenset[str] = frozenset()
    document: frozenset[str] = frozenset()
    diagram: frozenset[str] = frozenset()

    @classmethod
    def from_links(cls, links: Iterable[ResolvedArtifactLink]) -> "LinkedArtifactTypes":
        by_kind: dict[ArtifactLinkKind, set[str]] = {"entity": set(), "document": set(), "diagram": set()}
        for link in links:
            by_kind[link.kind].add(link.type_name)
        return cls(
            entity=frozenset(by_kind["entity"]),
            document=frozenset(by_kind["document"]),
            diagram=frozenset(by_kind["diagram"]),
        )

    def of_kind(self, kind: ReferenceKind) -> frozenset[str]:
        if kind == "document":
            return self.document
        if kind == "diagram":
            return self.diagram
        return self.entity


@dataclass(frozen=True)
class ReferenceTermVocabulary:
    """The three catalogs a reference term may name, bound to one repository.

    Built per repository because document types are repository-local while the other two are the
    deployment's. Construction reads the schemata once; ``load_document_schemata`` is itself cached,
    so a verification pass over many documents does not re-read them.
    """

    ontology: "OntologyCatalog"
    document_labels: Mapping[str, str]
    diagram_labels: Mapping[str, str]

    @classmethod
    def for_repository(
        cls, *, catalogs: "RuntimeCatalogs", repo_root: Path | None
    ) -> "ReferenceTermVocabulary":
        from src.application.artifacts.document_schema import load_document_schemata  # noqa: PLC0415

        schemata = load_document_schemata(repo_root) if repo_root is not None else {}
        return cls(
            ontology=catalogs.ontology,
            document_labels={
                doc_type: str(schema.get("name") or doc_type)
                for doc_type, schema in schemata.items()
            },
            diagram_labels={
                name: module.ui_config.label
                for name, module in catalogs.diagram_types.all_diagram_types().items()
            },
        )

    def status(self, term: str) -> TermStatus:
        parsed = parse_reference_term(term)
        if parsed.is_any:
            return TermStatus.KNOWN
        if parsed.kind == "entity":
            return TermStatus.KNOWN if self.ontology.expand_entity_type_term(parsed.body) else TermStatus.UNKNOWN
        if parsed.kind == "document":
            return TermStatus.KNOWN if parsed.body in self.document_labels else TermStatus.UNKNOWN
        # A diagram type the registry does not provide is still a type a stored diagram may name.
        return TermStatus.KNOWN if parsed.body in self.diagram_labels else TermStatus.UNREGISTERED

    def matches(self, term: str, linked: LinkedArtifactTypes) -> bool:
        parsed = parse_reference_term(term)
        present = linked.of_kind(parsed.kind)
        if parsed.kind == "entity":
            return self.ontology.entity_type_term_matches(parsed.body, set(present))
        return bool(present) if parsed.is_any else parsed.body in present

    def satisfied_by(self, term: str, link: ResolvedArtifactLink) -> bool:
        """Whether one link on its own satisfies *term* — the per-candidate form of `matches`."""
        return self.matches(term, LinkedArtifactTypes.from_links([link]))

    def label(self, term: str) -> str:
        """The term in the words a message should use it in."""
        parsed = parse_reference_term(term)
        if parsed.is_any:
            return _ANY_LABELS[parsed.kind]
        if parsed.kind == "entity":
            return self.ontology.format_entity_type_term(parsed.body)
        labels = self.document_labels if parsed.kind == "document" else self.diagram_labels
        return labels.get(parsed.body) or parsed.body.replace("-", " ").replace("_", " ")

    def kind_noun(self, term: str) -> str:
        return KIND_NOUNS[parse_reference_term(term).kind]
