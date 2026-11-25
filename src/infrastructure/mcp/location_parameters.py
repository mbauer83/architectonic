"""Every MCP tool parameter that names a location, and the confinement each one gets.

An MCP client is untrusted input: a tool argument naming a directory or a file was absolutised and
indexed, read or written as given, so `repo_root: "/"` made any read tool a way to read the server's
filesystem. Every call now passes through `confined_arguments` before the tool runs (the one dispatch
all four servers share, `name_normalization.install_call_tool_normalizer`), and the deciding is done
by `src.application.repository_confinement`, which the write path's authorization asks too.

The tables below are a register. `tests/architecture/test_every_location_parameter_is_confined.py`
fails when a tool declares a parameter whose name says it is a location and no row here says how it
is confined, or why it is not one.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import Enum
from pathlib import Path

from src.application.repository_confinement import (
    LocationRefused,
    confine_root,
    confine_within,
    require_segment,
)


class LocationKind(Enum):
    """How a parameter names a location, which decides the check it gets."""

    #: Names a repository: must be one of the configured repositories.
    REPOSITORY = "repository"
    #: Names the enterprise repository: must be the configured one.
    ENTERPRISE_REPOSITORY = "enterprise repository"
    #: Names a file, absolute or relative to the engagement repository: must lie inside a repository.
    FILE_IN_A_REPOSITORY = "file in a repository"
    #: Becomes one component of a path (a collection's directory): must be a single name.
    PATH_COMPONENT = "path component"


#: Parameters that mean the same thing on every tool that declares them.
LOCATION_PARAMETERS: Mapping[str, LocationKind] = {
    "repo_root": LocationKind.REPOSITORY,
    "enterprise_root": LocationKind.ENTERPRISE_REPOSITORY,
    "group": LocationKind.PATH_COMPONENT,
    "new_slug": LocationKind.PATH_COMPONENT,
}

#: Parameters whose name means a location on one tool only.
TOOL_LOCATION_PARAMETERS: Mapping[tuple[str, str], LocationKind] = {
    ("artifact_verify", "path"): LocationKind.FILE_IN_A_REPOSITORY,
    ("artifact_group", "target"): LocationKind.PATH_COMPONENT,
}

#: Names that look like locations and are not, each with the reason.
NOT_LOCATIONS: Mapping[str, str] = {
    "authored_groupings": "boxes drawn in a diagram's layout, stored in its frontmatter",
    "direction": "a layout or traversal direction",
    "file_type": "which kind of artifact to verify a file as, from a closed set",
    "group_by": "a statistic's grouping attribute",
    "group_id": "an assurance group's id, looked up in the confidential store",
    "group_mapping_resolutions": "how promotion maps engagement groups onto enterprise ones, by name",
    "purl": "a package URL identifying a component, never fetched",
    "slug": "a viewpoint's key within the repository's one viewpoint file",
    "source": "a label naming where security signals came from",
    "source_entity": "an artifact id, looked up in the index",
    "source_format": "an image format, from a closed set",
    "source_id": "an assurance node id, looked up in the store",
    "target": "where a change is saved (engagement or enterprise), or a guidance topic",
    "target_entity": "an artifact id, looked up in the index",
    "target_id": "an assurance node id, looked up in the store",
    "targets": "where a scratchpad note is lifted to, as model choices",
}


def location_kind(tool: str, parameter: str) -> LocationKind | None:
    """How `parameter` of `tool` names a location, or None when it names none."""
    return TOOL_LOCATION_PARAMETERS.get((tool, parameter)) or LOCATION_PARAMETERS.get(parameter)


def _configured(resolve: Callable[[], Path]) -> tuple[Path, ...]:
    try:
        return (resolve(),)
    except RuntimeError:
        return ()


def _engagement() -> tuple[Path, ...]:
    from src.infrastructure.mcp.artifact_mcp.context import (  # noqa: PLC0415
        default_engagement_repo_root,
        workspace_root,
    )

    return tuple(
        root if root.is_absolute() else workspace_root() / root
        for root in _configured(default_engagement_repo_root)
    )


def _enterprise() -> tuple[Path, ...]:
    from src.infrastructure.mcp.artifact_mcp.context import default_enterprise_repo_root  # noqa: PLC0415

    return _configured(default_enterprise_repo_root)


def _confined(kind: LocationKind, value: str, parameter: str) -> str:
    match kind:
        case LocationKind.REPOSITORY:
            return str(confine_root(Path(value), _engagement() + _enterprise()))
        case LocationKind.ENTERPRISE_REPOSITORY:
            return str(confine_root(Path(value), _enterprise()))
        case LocationKind.FILE_IN_A_REPOSITORY:
            engagement = _engagement()
            given = Path(value).expanduser()
            candidate = given if given.is_absolute() or not engagement else engagement[0] / given
            return str(confine_within(candidate, engagement + _enterprise()))
        case LocationKind.PATH_COMPONENT:
            return require_segment(value, what=f"'{parameter}'")


def confined_arguments(tool: str, arguments: Mapping[str, object]) -> dict[str, object]:
    """`arguments` with every location confined: a root becomes the configured root it names.

    Raises `LocationRefused` for a location outside the configured repositories.
    """
    confined = dict(arguments)
    for parameter, value in arguments.items():
        kind = location_kind(tool, parameter)
        if kind is None or value is None or value == "":
            continue
        if not isinstance(value, str):
            raise LocationRefused(f"'{parameter}' must be a string naming a location.")
        confined[parameter] = _confined(kind, value, parameter)
    return confined
