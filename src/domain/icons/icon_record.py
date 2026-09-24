"""A shared icon of the repository's library, as the index sees it: what its file says, and where."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.domain.icons.icon_file import IconMetadata


@dataclass(frozen=True)
class IconRecord:
    """The picture itself is not held here. It is read from the file when it is drawn or served, so
    the index costs a line of metadata per icon rather than its bytes."""

    metadata: IconMetadata
    path: Path

    @property
    def artifact_id(self) -> str:
        return self.metadata.artifact_id
