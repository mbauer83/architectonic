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

from src.infrastructure.rest.contracts.artifact_home import FiledOnCreate, Rehomeable


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateEntityBody(_Body, FiledOnCreate):
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


class EditEntityBody(_Body, Rehomeable):
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
