import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal, TypeAlias


class Severity:
    ERROR: Final[Literal["error"]] = "error"
    WARNING: Final[Literal["warning"]] = "warning"


SeverityLiteral: TypeAlias = Literal["error", "warning"]
VerificationFileType: TypeAlias = Literal["entity", "connection", "diagram", "document"]


@dataclass(frozen=True)
class Issue:
    severity: SeverityLiteral
    code: str
    message: str
    location: str
    details: Mapping[str, Any] | None = None
    actions: tuple[Mapping[str, Any], ...] | None = None


@dataclass
class VerificationResult:
    path: Path
    file_type: VerificationFileType
    issues: list[Issue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    def __repr__(self) -> str:
        status = "PASS" if self.valid else "FAIL"
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


ENTITY_ID_RE = re.compile(r"^[A-Z]{2,6}@\d+\.[A-Za-z0-9_-]+\..+$")


def connection_header_matches_shape(header: str) -> bool:
    """Check whether a connection header from an .outgoing.md ``### `` line is valid.

    Expected format: ``{connection-type} → {target-entity-id}``
    """
    if " → " not in header:
        return False
    parts = header.split(" → ", 1)
    return len(parts) == 2 and bool(parts[0].strip()) and bool(parts[1].strip())


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
