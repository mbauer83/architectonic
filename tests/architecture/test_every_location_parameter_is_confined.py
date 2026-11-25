"""Every client-supplied parameter that names a location is confined to the configured repositories.

The register for `src.application.repository_confinement`. A parameter is found by its name — the
words a location is called by — on every MCP tool of the four servers and on every REST operation's
path, query and body. Each must be either confined or stated not to be a location, with the reason:

* an MCP parameter, by a row in `location_parameters` (which `confined_arguments` enforces at the
  one dispatch all four servers share);
* a REST parameter, by declaring the published segment pattern (`PathComponent`), checked here in
  the served OpenAPI document — so the row is evidence of the enforcement, not a claim about it.

Adding a tool or a route that takes `output_dir` or `source_path` fails this until somebody decides.

Regression: `repo_root: "/"` on any MCP read tool indexed and served the server's filesystem, and a
`group` of `../../elsewhere` filed a written artifact outside the repository.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from src.application.repository_confinement import SEGMENT_PATTERN
from src.infrastructure.mcp.location_parameters import (
    LOCATION_PARAMETERS,
    NOT_LOCATIONS,
    TOOL_LOCATION_PARAMETERS,
)

#: The words a location is called by.
_LOCATION_NAME = re.compile(r"root|path|dir|file|folder|slug|group|location|url|dest|source|target", re.I)

#: REST parameters whose names look like locations and are not, keyed `(in, name)`.
REST_NOT_LOCATIONS: dict[tuple[str, str], str] = {
    ("body", "authored_groupings"): "boxes drawn in a diagram's layout, stored in its frontmatter",
    ("body", "grouping_intents"): "how a diagram's boxes are grouped, stored in its frontmatter",
    ("body", "group_id"): "an assurance group's id, looked up in the confidential store",
    ("body", "group_mapping_resolutions"): "how promotion maps engagement groups onto enterprise ones",
    ("body", "slugs"): "viewpoint keys within the repository's one viewpoint file",
    ("body", "source"): "a label naming where security signals came from",
    ("body", "source_bindings"): "GSN elements a publication binds, by id",
    ("body", "source_entity"): "an artifact id, looked up in the index",
    ("body", "source_format"): "an image format, from a closed set",
    ("body", "source_id"): "an assurance node id, looked up in the store",
    ("body", "target_entity"): "an artifact id, looked up in the index",
    ("body", "target_id"): "an assurance node id, looked up in the store",
    ("body", "targets"): "where a scratchpad note is lifted to, as model choices",
    ("path", "group_id"): "an assurance group's id, looked up in the confidential store",
    ("query", "direction"): "a traversal direction",
    ("query", "group"): "a filter compared with each listed artifact's collection, never joined to a path",
    ("query", "purl"): "a package URL identifying a component, never fetched",
    ("query", "source_id"): "an artifact id, looked up in the index",
    ("query", "source_type"): "an artifact type name",
    ("query", "target"): "a guidance topic",
    ("query", "target_id"): "an artifact id, looked up in the index",
    ("query", "target_type"): "an artifact type name",
}

#: A `slug` is a viewpoint's key on these operations, and a collection's directory elsewhere.
_VIEWPOINT_SLUG_OPERATIONS = re.compile(r"^/api/viewpoints/")


def _mcp_parameters() -> list[tuple[str, str]]:
    from src.infrastructure.mcp.mcp_artifact_server import mcp_read, mcp_write
    from src.infrastructure.mcp.mcp_assurance_server import mcp_assurance_read, mcp_assurance_write

    return sorted({
        (tool.name, parameter)
        for server in (mcp_read, mcp_write, mcp_assurance_read, mcp_assurance_write)
        for tool in server._tool_manager.list_tools()
        for parameter in (tool.parameters.get("properties") or {})
        if _LOCATION_NAME.search(parameter)
    })


def test_every_mcp_location_parameter_is_confined_or_explained() -> None:
    undecided = [
        (tool, parameter) for tool, parameter in _mcp_parameters()
        if (tool, parameter) not in TOOL_LOCATION_PARAMETERS
        and parameter not in LOCATION_PARAMETERS
        and parameter not in NOT_LOCATIONS
    ]

    assert undecided == [], (
        "these MCP parameters are named like locations and no row in "
        "src/infrastructure/mcp/location_parameters.py says how they are confined or why they are "
        f"not locations: {undecided}"
    )


def test_the_register_names_no_parameter_that_no_tool_declares() -> None:
    declared = {parameter for _tool, parameter in _mcp_parameters()}
    declared_pairs = set(_mcp_parameters())

    assert set(LOCATION_PARAMETERS) - declared == set()
    assert set(TOOL_LOCATION_PARAMETERS) - declared_pairs == set()
    assert set(NOT_LOCATIONS) - declared == set()


def _schemas() -> tuple[dict[str, Any], dict[str, Any]]:
    from src.infrastructure.backend.arch_backend_app import _build_app

    document = _build_app().openapi()
    return document, document["components"]["schemas"]


def _properties(schema: dict[str, Any], schemas: dict[str, Any], seen: tuple[str, ...] = ()) -> dict[str, Any]:
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return {} if name in seen else _properties(schemas[name], schemas, (*seen, name))
    found: dict[str, Any] = {}
    for key in ("anyOf", "oneOf", "allOf"):
        for alternative in schema.get(key, []):
            found.update(_properties(alternative, schemas, seen))
    found.update(schema.get("properties", {}))
    return found


def _patterns(schema: dict[str, Any]) -> set[str | None]:
    alternatives = [a for a in schema.get("anyOf", [schema]) if a.get("type") != "null"]
    return {alternative.get("pattern") for alternative in alternatives}


def _rest_parameters() -> list[tuple[str, str, str, dict[str, Any]]]:
    document, schemas = _schemas()
    found: list[tuple[str, str, str, dict[str, Any]]] = []
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            where = f"{method.upper()} {path}"
            for parameter in operation.get("parameters", []):
                if _LOCATION_NAME.search(parameter["name"]):
                    found.append((where, parameter["in"], parameter["name"], parameter.get("schema", {})))
            for media in operation.get("requestBody", {}).get("content", {}).values():
                for name, schema in _properties(media.get("schema", {}), schemas).items():
                    if _LOCATION_NAME.search(name):
                        found.append((where, "body", name, schema))
    return found


@pytest.fixture(scope="module")
def rest_parameters() -> list[tuple[str, str, str, dict[str, Any]]]:
    return _rest_parameters()


def _is_explained(where: str, located_in: str, name: str) -> bool:
    """Whether a row says this parameter is not a location. A viewpoint's slug keys one file."""
    if (located_in, name) in REST_NOT_LOCATIONS:
        return True
    return name == "slug" and bool(
        _VIEWPOINT_SLUG_OPERATIONS.match(where.split(" ", 1)[1])
    )


def test_every_rest_location_parameter_declares_the_segment_pattern(
    rest_parameters: list[tuple[str, str, str, dict[str, Any]]],
) -> None:
    unconfined = [
        (where, located_in, name)
        for where, located_in, name, schema in rest_parameters
        if not _is_explained(where, located_in, name) and _patterns(schema) != {SEGMENT_PATTERN}
    ]

    assert unconfined == [], (
        "these REST parameters are named like locations and neither declare PathComponent "
        "(src/infrastructure/rest/contracts/path_components.py) nor have a REST_NOT_LOCATIONS row "
        f"saying why they are not locations: {unconfined}"
    )


def test_no_rest_exemption_outlives_its_parameter(
    rest_parameters: list[tuple[str, str, str, dict[str, Any]]],
) -> None:
    present = {(located_in, name) for _where, located_in, name, _schema in rest_parameters}

    assert set(REST_NOT_LOCATIONS) - present == set()
