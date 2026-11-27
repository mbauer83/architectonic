import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeAlias

from src.domain.artifact_id import PREFIX_PATTERN, RANDOM_KEY_PATTERN
from src.domain.repository.artifact_location import ArtifactKindName, VerifiedArtifactKindName
from src.domain.repository.connection_declaration import parse_connection_header
from src.domain.verification_findings import Issue, Severity, SeverityCounts, SeverityLiteral, count_severities

# Re-exported: the finding vocabulary is the domain's, so a diagram-type module implementing a
# domain verification port does not have to reach up here for it.
__all__ = ["Issue", "Severity", "SeverityCounts", "SeverityLiteral", "count_severities"]

#: The kinds the verifier takes, which is a fact each kind's row declares.
VerificationFileType: TypeAlias = VerifiedArtifactKindName

#: Whether a kind's own verifier looked at the file. `unverified` is the answer for a file of a kind no
#: verifier is bound to: it may still carry the findings every kind is held to, but nothing has said
#: the file is right, so it is never counted as passed.
VerificationOutcome: TypeAlias = Literal["verified", "unverified"]


@dataclass
class VerificationResult:
    path: Path
    file_type: ArtifactKindName | Literal["unrecognised"]
    issues: list[Issue] = field(default_factory=list)
    outcome: VerificationOutcome = "verified"

    @property
    def valid(self) -> bool:
        """Whether the file passed: its kind's verifier looked at it and found no error."""
        return self.outcome == "verified" and not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def advice(self) -> list[Issue]:
        """Modelling heuristics: never part of `valid`, never counted as warnings."""
        return [i for i in self.issues if i.severity == Severity.ADVICE]

    @property
    def counts(self) -> SeverityCounts:
        return count_severities(i.severity for i in self.issues)

    def __repr__(self) -> str:
        status = "PASS" if self.valid else "FAIL" if self.outcome == "verified" else "UNVERIFIED"
        return f"VerificationResult({status}, {self.path.name}, {len(self.issues)} issues)"


@dataclass(frozen=True)
class VerifierRuntimeConfig:
    mode: Literal["full", "incremental"]
    state_dir: Path
    changed_ratio_threshold: float
    changed_count_threshold: int
    log_mode: bool


@dataclass
class IncrementalState:
    schema_version: int
    engine_signature: str
    include_diagrams: bool
    git_head: str | None
    snapshots: dict[str, dict[str, int | str]]
    results: dict[str, dict]
    include_registry: bool = True  # added: invalidate cache if registry availability changes


@dataclass(frozen=True)
class ConnectionRefs:
    source_ids: tuple[str, ...]
    target_ids: tuple[str, ...]


def entity_id_from_path(path: Path) -> str:
    """Return the artifact-id from a file path (full stem)."""
    return path.stem


#: A *full* artifact id — this one insists on the slug, where `artifact_id` accepts the short form too,
#: which is why it is its own pattern rather than a re-export. The random key is taken from the
#: canonical module rather than restated: the two spellings of that charset disagreed for a release,
#: and the copy that was right was this one.
ENTITY_ID_RE = re.compile(rf"^{PREFIX_PATTERN}@\d+\.{RANDOM_KEY_PATTERN}\..+$")


def connection_header_matches_shape(header: str) -> bool:
    """Whether a connection header from an `.outgoing.md` `### ` line is valid.

    Asks `connection_declaration`, which owns the grammar, rather than re-deciding it. The reading
    this replaces required only a ` → ` with non-empty sides, so it accepted a header the parser then
    declined — and the shape check and the parse disagreeing is how a section reads as valid to one
    half of the verifier and as absent to the other.
    """
    return parse_connection_header(header) is not None


VALID_STATUSES: frozenset[str] = frozenset({"draft", "active", "deprecated"})

# --- Frontmatter schemata (per file-type) -----------------------------------
# These define the *required* frontmatter fields for each of the three file
# types.  Repository configuration may extend (but not override or remove)
# these sets.

ENTITY_REQUIRED: frozenset[str] = frozenset(
    {
        "artifact-id",
        "artifact-type",
        "name",
        "version",
        "status",
        "last-updated",
    }
)

ENTITY_OPTIONAL: frozenset[str] = frozenset(
    {
        "keywords",
    }
)

OUTGOING_FILE_REQUIRED: frozenset[str] = frozenset(
    {
        "source-entity",
        "version",
        "status",
        "last-updated",
    }
)

DIAGRAM_REQUIRED: frozenset[str] = frozenset(
    {
        "artifact-id",
        "artifact-type",
        "name",
        "diagram-type",
        "version",
        "status",
        "last-updated",
    }
)

DIAGRAM_OPTIONAL: frozenset[str] = frozenset(
    {
        "keywords",
    }
)

DIAGRAM_ARTIFACT_TYPES: frozenset[str] = frozenset({"diagram"})
