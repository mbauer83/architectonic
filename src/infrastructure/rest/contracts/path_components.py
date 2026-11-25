"""A request field whose value becomes one component of a path inside a repository.

A collection's slug names its directory, so `group: "../../elsewhere"` filed an artifact outside the
repository. Such fields are declared with this type, which publishes the rule
(`repository_confinement.SEGMENT_PATTERN`) as the field's pattern: the request is refused before a
handler runs, and the OpenAPI document states what is accepted.
`tests/architecture/test_every_location_parameter_is_confined.py` holds every such field to it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Path
from pydantic import StringConstraints

from src.application.repository_confinement import SEGMENT_PATTERN

#: One path component: a collection's slug, a file name.
PathComponent = Annotated[str, StringConstraints(pattern=SEGMENT_PATTERN)]

#: The same rule for a path parameter of a route (`/api/groups/{kind}/{slug}`).
PathComponentParameter = Annotated[str, Path(pattern=SEGMENT_PATTERN)]
