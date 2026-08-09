"""The safety hints every MCP tool announces itself with, as a closed set of presets.

MCP's four hints — read-only, destructive, idempotent, open-world — are what a host warns a user
with before it invokes a tool, so a tool that declares none is one a host cannot warn about. Every
tool on every mount carries one of these presets, and `test_mcp_config_entrypoints` holds all four
mounts to it.

Presets rather than per-tool tuples, and one module rather than one per surface: the artifact tools
were annotated from a copy that lived under `artifact_mcp/`, which put the vocabulary inside one of
the two surfaces that needed it and left the assurance tools with none at all for as long as
reaching it would have been a layering inversion. A classification belongs at the registration
site; the words it is spelled with belong here.
"""

from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

LOCAL_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

#: An additive write that a caller may safely repeat. Distinct from `LOCAL_WRITE` because the
#: hint is what tells a host a retry after a dropped response is free; `assurance_assign_provenance`
#: is set-once by construction, so re-asserting the same analysis genuinely changes nothing, and
#: saying otherwise would make a host warn about the one write it never needs to warn about.
IDEMPOTENT_LOCAL_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

DESTRUCTIVE_LOCAL_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)

OPEN_WORLD_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

DESTRUCTIVE_OPEN_WORLD_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)
