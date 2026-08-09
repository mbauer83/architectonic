from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol, TypeAlias, runtime_checkable

from src.domain.repository.repo_scope import MountScope, infer_repo_scope

Domain: TypeAlias = str


@dataclass(frozen=True)
class RepoMount:
    root: Path
    scope: MountScope
    engagement_label: str


class DuplicateArtifactIdError(ValueError):
    pass


def infer_engagement_label(root: Path, *, scope: MountScope) -> str:
    if scope == "enterprise":
        return "enterprise"
    parts = root.resolve().parts
    if "engagements" in parts:
        idx = parts.index("engagements")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def infer_mount(root: Path) -> RepoMount:
    resolved = root.resolve()
    scope: MountScope = "enterprise" if infer_repo_scope(resolved) == "enterprise" else "engagement"
    return RepoMount(root=resolved, scope=scope, engagement_label=infer_engagement_label(resolved, scope=scope))


@dataclass(frozen=True)
class EntityRecord:
    artifact_id: str
    artifact_type: str
    name: str
    version: str
    status: str
    domain: Domain
    subdomain: str
    path: Path
    keywords: tuple[str, ...]
    extra: Mapping[str, object]
    content_text: str
    display_blocks: Mapping[str, str]
    display_label: str
    display_alias: str
    host_diagram_id: str | None = None
    """None for model entities; the owning diagram's artifact_id for diagram-only entities."""
    group: str = "uncategorized"
    specializations: tuple[str, ...] = ()
    """Every applied specialization slug, in declaration order. Canonical for resolution,
    rendering, and styling.

    A scalar ``specialization`` sat beside this holding the first element, kept consistent in
    ``__post_init__`` so a caller could set either. Two spellings of one fact is a standing
    invitation to disagree, and the reconciliation existed only to stop them — a consumer wanting
    the primary reads ``specializations[0]``, which says what it is taking."""
    attributes: Mapping[str, object] = field(default_factory=dict)
    """Typed values decoded from the entity's Properties table (the user-facing
    attribute surface). Distinct from `extra`, which carries frontmatter fields —
    attribute reads consult this first, then fall back to `extra`."""
    last_updated: str | None = None
    """The `last-updated` frontmatter stamp (UTC ISO-8601, e.g. 2026-07-24T09:15:00Z).
    None for records with no stamp — diagram-only entities and pre-migration repos that
    predate the field. Surfaced through the REST/MCP summaries as `last_updated`."""

    def __str__(self) -> str:
        return (
            f"[{self.artifact_id}] {self.name}  "
            f"({self.artifact_type} · {self.domain}/{self.subdomain} · "
            f"status={self.status})"
        )


@dataclass(frozen=True)
class ConnectionRecord:
    artifact_id: str
    source: str
    target: str
    conn_type: str
    version: str
    status: str
    path: Path
    extra: Mapping[str, object]
    content_text: str
    associated_entities: tuple[str, ...] = field(default_factory=tuple)
    src_multiplicity: str = ""
    tgt_multiplicity: str = ""
    group: str = "uncategorized"
    specializations: tuple[str, ...] = ()
    """Every applied connection specialization slug, in declaration order — see EntityRecord."""
    attributes: Mapping[str, object] = field(default_factory=dict)
    """Typed values from the connection's metadata block, excluding specialization."""
    last_updated: str | None = None
    """The owning outgoing file's `last-updated` stamp (UTC ISO-8601); None when absent.
    Every connection declared in one file shares it — the file is the unit that is written."""

    @property
    def source_ids(self) -> list[str]:
        return [self.source]

    @property
    def target_ids(self) -> list[str]:
        return [self.target]

    def involves(self, entity_id: str) -> bool:
        return entity_id in self.source_ids or entity_id in self.target_ids

    def __str__(self) -> str:
        return f"[{self.artifact_id}]  {self.source} --{self.conn_type}--> {self.target}  (status={self.status})"


@dataclass(frozen=True)
class DiagramRecord:
    artifact_id: str
    artifact_type: str
    name: str
    diagram_type: str
    version: str
    status: str
    path: Path
    extra: Mapping[str, object]
    group: str = "uncategorized"
    last_updated: str | None = None
    """The `last-updated` frontmatter stamp (UTC ISO-8601); None when the file carries none."""

    def __str__(self) -> str:
        return f"[{self.artifact_id}] {self.name}  ({self.diagram_type} · status={self.status})"


@dataclass(frozen=True)
class DocumentRecord:
    artifact_id: str
    doc_type: str
    title: str
    status: str
    path: Path
    keywords: tuple[str, ...]
    sections: tuple[str, ...]  # heading text of ## sections, in order
    content_text: str
    extra: Mapping[str, object]  # frontmatter fields beyond standard ones
    group: str = "uncategorized"
    last_updated: str | None = None
    """The `last-updated` frontmatter stamp (UTC ISO-8601); None when the file carries none."""


def summary_from_document(rec: DocumentRecord) -> "ArtifactSummary":
    return ArtifactSummary(
        artifact_id=rec.artifact_id,
        artifact_type=rec.doc_type,
        name=rec.title,
        version=str(rec.extra.get("version", "")),
        status=rec.status,
        record_type="document",
        path=rec.path,
        group=rec.group,
        last_updated=rec.last_updated,
    )


STANDARD_DOCUMENT_FIELDS = frozenset(
    {
        "artifact-id",
        "artifact-type",
        "doc-type",
        "title",
        "status",
        "version",
        "last-updated",
        "keywords",
    }
)


#: How a note's address is composed from the scratchpad's and the note's own id. The same shape a
#: diagram already uses for the constructs it owns (`{diagram_id}#swimlane/sw-1`), because the
#: question is the same one: a searchable unit that has no file of its own.
NOTE_ADDRESS_INFIX = "#note/"


def scratchpad_note_id(scratchpad_id: str, note_id: str) -> str:
    """The address a note is findable at. Local ids are unique within their scratchpad only."""
    return f"{scratchpad_id}{NOTE_ADDRESS_INFIX}{note_id}"


@dataclass(frozen=True)
class ScratchpadNoteRecord:
    """One note on a scratchpad, as the index sees it.

    The only searchable unit whose text lives *inside* another artifact's file: a scratchpad is
    loaded, saved and versioned whole, but what someone searches for is a thought, and a thought is
    a note. So the note is the record and the scratchpad is its container — `path` is the
    scratchpad's file, and `artifact_id` is composed rather than stored.

    A note is deliberately *thinner* than an entity. It has no version of its own, no keywords, and
    a type only if someone has decided one — which is the whole point of the feature, and the reason
    `score_scratchpad_note` weighs it below everything a person committed to.
    """

    artifact_id: str
    scratchpad_id: str
    scratchpad_name: str
    note_id: str
    title: str
    body: str
    #: Empty until decided. A note that has reached only its domain has still decided something.
    element_type: str
    domain: str
    area: str
    status: str
    path: Path
    group: str = "uncategorized"
    last_updated: str | None = None

    def __str__(self) -> str:
        return f"[{self.artifact_id}] {self.title}  (note on {self.scratchpad_name})"


# ── The searchable-kind vocabulary, in one place ─────────────────────────────
# Two spellings of the same list, and they have to agree: `RecordType` is the discriminator on an
# individual hit, `SearchableKind` the member of the include-set that gates which kinds participate.
# Both were previously restated in `application/artifacts/_search.py`, in `artifacts/repository.py`,
# on `SearchHit` below and in the REST contract — four copies of one vocabulary, which is how a fifth
# kind becomes a hunt rather than an edit.
RecordType: TypeAlias = Literal["entity", "connection", "diagram", "document", "scratchpad-note"]
SearchableKind: TypeAlias = Literal[
    "entities", "connections", "diagrams", "documents", "scratchpad-notes"
]

#: Kind → the record type its hits carry. The plural is what a caller asks for; the singular is what
#: it gets back. Typed `str` → `str` rather than Literal → Literal because every caller looks a
#: *runtime* value up in it — an FTS row's `record_type` column, a request's `include_` flag — and a
#: narrower key type only moves the narrowing to the call site.
KIND_TO_RECORD_TYPE: Mapping[str, str] = MappingProxyType(
    {
        "entities": "entity",
        "connections": "connection",
        "diagrams": "diagram",
        "documents": "document",
        "scratchpad-notes": "scratchpad-note",
    }
)
RECORD_TYPE_TO_KIND: Mapping[str, str] = MappingProxyType(
    {record_type: kind for kind, record_type in KIND_TO_RECORD_TYPE.items()}
)
ALL_SEARCHABLE_KINDS: frozenset[str] = frozenset(KIND_TO_RECORD_TYPE)

#: Kinds that must never outrank the others, whatever they score. A note is a half-formed thought
#: and an entity is a commitment, so a scratchpad can never push model content down a result list —
#: the condition the feature was allowed into the index under.
SUBORDINATE_RECORD_TYPES: frozenset[str] = frozenset({"scratchpad-note"})


@dataclass
class SearchHit:
    score: float
    record_type: RecordType
    record: EntityRecord | ConnectionRecord | DiagramRecord | DocumentRecord | ScratchpadNoteRecord

    def __str__(self) -> str:
        return f"  score={self.score:.3f}  {self.record}"


@dataclass
class SearchResult:
    query: str
    hits: list[SearchHit] = field(default_factory=list)

    def __str__(self) -> str:
        if not self.hits:
            return f"No results for '{self.query}'"
        lines = [f"Search results for '{self.query}' ({len(self.hits)} hits):"]
        for hit in self.hits:
            lines.append(str(hit))
        return "\n".join(lines)


@dataclass(frozen=True)
class ArtifactSummary:
    artifact_id: str
    artifact_type: str
    name: str
    version: str
    status: str
    record_type: Literal["entity", "connection", "diagram", "document"]
    path: Path
    host_diagram_id: str | None = None
    """None for model entities; the owning diagram's artifact_id for diagram-only entities.

    When present, this entity exists only within that diagram's diagram-entities frontmatter.
    It has no standalone file. The ``path`` field points to the diagram file, not an entity
    file. To author or edit this entity, open the owning diagram.
    """
    group: str = "uncategorized"
    last_updated: str | None = None
    """When the artifact was last written, as ``YYYY-MM-DDTHH:MM:SSZ`` (UTC); None for
    artifacts with no stamp. Lexical order equals chronological order, so callers may sort
    on the raw string."""

    def __str__(self) -> str:
        label = f" {self.name}" if self.name else ""
        scope = f" [diagram-only:{self.host_diagram_id}]" if self.host_diagram_id else ""
        return f"[{self.artifact_id}]{label}  ({self.artifact_type} · {self.record_type} · status={self.status}){scope}"


def summary_from_entity(rec: EntityRecord) -> ArtifactSummary:
    return ArtifactSummary(
        artifact_id=rec.artifact_id,
        artifact_type=rec.artifact_type,
        name=rec.name,
        version=rec.version,
        status=rec.status,
        record_type="entity",
        path=rec.path,
        host_diagram_id=rec.host_diagram_id,
        group=rec.group,
        last_updated=rec.last_updated,
    )


def summary_from_connection(rec: ConnectionRecord) -> ArtifactSummary:
    return ArtifactSummary(
        artifact_id=rec.artifact_id,
        artifact_type="connection",
        name="",
        version=rec.version,
        status=rec.status,
        record_type="connection",
        path=rec.path,
        group=rec.group,
        last_updated=rec.last_updated,
    )


def summary_from_diagram(rec: DiagramRecord) -> ArtifactSummary:
    return ArtifactSummary(
        artifact_id=rec.artifact_id,
        artifact_type=rec.artifact_type,
        name=rec.name,
        version=rec.version,
        status=rec.status,
        record_type="diagram",
        path=rec.path,
        group=rec.group,
        last_updated=rec.last_updated,
    )


@runtime_checkable
class SemanticSearchProvider(Protocol):
    def top_k(self, query: str, k: int, *, threshold: float = 0.75) -> list[tuple[float, str]]: ...


STANDARD_ENTITY_FIELDS = frozenset(
    {
        "artifact-id",
        "artifact-type",
        "name",
        "version",
        "status",
        "last-updated",
        "keywords",
        "specialization",
    }
)

STANDARD_OUTGOING_FIELDS = frozenset(
    {
        "source-entity",
        "version",
        "status",
        "last-updated",
    }
)

STANDARD_DIAGRAM_FIELDS = frozenset(
    {
        "artifact-id",
        "artifact-type",
        "name",
        "diagram-type",
        "version",
        "status",
        "last-updated",
        "keywords",
    }
)
