"""What each application-level ``AnalysisInvalid`` / ``BindInvalid`` string means, for both surfaces.

The use cases carry a free-form ``error`` string, and the closed ``ErrorCode`` union is what clients
branch on, so something has to translate. That translation was written once, for HTTP, and lived
beside the router that raised it.

It is not an HTTP fact. MCP refuses with the same vocabulary and needs the same answer, and a second
copy over there would be a second vocabulary one commit later — which is the exact defect
``mcp.execution_failure`` exists to prevent, reintroduced at a different address. So the tables live
here, in ``rest.contracts``, which both surfaces already depend on for ``ErrorCode`` itself. The HTTP
*status* rides along because it is keyed by the same string and splitting the table in two would
leave two things to keep in sync instead of one; MCP reads the code and the field and ignores the
status, which has no meaning on a JSON-RPC surface.

``tests/assurance/test_analysis_invalid_mapping.py`` extracts every code the use cases construct and
fails when one is missing here.
"""

from __future__ import annotations

from src.infrastructure.rest.contracts.errors import ErrorCode

#: Which field each rejected-value code is about, so a refusal can carry a path a client highlights
#: rather than prose it has to parse.
REJECTED_FIELD: dict[str, str] = {
    "missing_name": "name",
    "invalid_method": "method",
    "invalid_status": "status",
}

#: The status and code each application-level invalid maps to. Exhaustive over what the use cases
#: construct; the accompanying test is what keeps it that way.
INVALID_MAPPING: dict[str, tuple[int, ErrorCode]] = {
    "missing_name": (422, "validation_error"),
    "invalid_method": (422, "validation_error"),
    "invalid_status": (422, "validation_error"),
    "group_not_found": (404, "not_found"),
    "analysis_not_empty": (409, "analysis_not_empty"),
}

#: The bind use case's own invalids. Neither needs a new vocabulary member: one is a state conflict
#: and the other a rejected value, which the closed union already names.
BIND_INVALID_MAPPING: dict[str, tuple[int, ErrorCode]] = {
    # The node is not in the state this operation applies to — nothing the caller sent is wrong.
    "invalid_binding_status": (409, "conflict"),
    # A type name the ontology does not know: a rejected value, so it carries its field.
    "unknown_arch_type": (422, "validation_error"),
}

BIND_REJECTED_FIELD: dict[str, str] = {"unknown_arch_type": "suggested_arch_type"}
