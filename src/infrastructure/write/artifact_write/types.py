from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WriteResult:
    wrote: bool
    path: Path
    artifact_id: str
    content: str | None
    warnings: list[str]
    verification: dict[str, Any] | None

    @property
    def error_messages(self) -> list[str]:
        """What the verification refused, one message per error; empty when it refused nothing."""
        issues = (self.verification or {}).get("issues", [])
        return [str(issue.get("message")) for issue in issues if issue.get("severity") == "error"]


@dataclass(frozen=True)
class SyncDiagramToModelResult(WriteResult):
    """WriteResult extended with lists of IDs pruned during diagram-to-model sync."""

    removed_entity_ids: list[str] = field(default_factory=list)
    removed_connection_ids: list[str] = field(default_factory=list)
    deleted_diagram: bool = False
