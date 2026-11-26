"""A route's path parameter whose value becomes one component of a path inside a repository.

The rule for a body field (`artifact_home_wire.PathComponent`), stated for a path parameter, which
only the HTTP transport has: it publishes `repository_confinement.SEGMENT_PATTERN` as the parameter's
pattern, so the request is refused before a handler runs and the OpenAPI document states it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Path

from src.application.repository_confinement import SEGMENT_PATTERN

#: One path component as a path parameter of a route (`/api/groups/{kind}/{slug}`).
PathComponentParameter = Annotated[str, Path(pattern=SEGMENT_PATTERN)]
