"""The request bodies the entity write operations accept.

Beside the router rather than inside it, the way the diagram surface already keeps its own
(`diagrams/_write_bodies.py`). A body is a declaration about what a caller may send; a handler is
what happens when they do, and the two grow at different rates — the router had reached the length
policy's ceiling and could not take another field until they were apart.

`extra="forbid"` is the reason the field vocabulary here has to be exact rather than approximately
right: a caller sending a name this module does not declare is refused outright, not ignored.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from src.domain.repository.groups import UNCATEGORIZED


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _FiledOnCreate(_Body):
    """A body that says where the artifact it creates is filed."""

    #: Which model-project collection the artifact is filed in — its *home*. Absent means
    #: `uncategorized`, the same reading the write path and every MCP twin already take.
    group: str | None = None

    def home(self) -> str:
        """The collection to place it in, absent reading as the uncategorized one.

        A method rather than the call site's `or UNCATEGORIZED`, so the reading of an absent home is
        stated once for every surface that creates something.
        """
        return self.group or UNCATEGORIZED


class _Rehomeable(_Body):
    """A body that can move the artifact it edits."""

    #: Move the artifact to this collection. Absent leaves it where it is; naming `uncategorized`
    #: is how a re-home *out* of a collection is said, because that is a real collection rather
    #: than the absence of one.
    group: str | None = None


class CreateEntityBody(_FiledOnCreate):
    artifact_type: str
    name: str
    summary: str | None = None
    properties: dict[str, Any] | None = None
    attribute_types: dict[str, str] | None = None
    notes: str | None = None
    keywords: list[str] | None = None
    specializations: list[str] | None = None
    version: str = "0.1.0"
    status: str = "draft"
    dry_run: bool = True


class EditEntityBody(_Rehomeable):
    name: str | None = None
    summary: str | None = None
    properties: dict[str, Any] | None = None
    attribute_types: dict[str, str] | None = None
    notes: str | None = None
    keywords: list[str] | None = None
    specializations: list[str] | None = None
    version: str | None = None
    status: str | None = None
    dry_run: bool = True
