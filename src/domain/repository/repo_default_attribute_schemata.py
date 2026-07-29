"""Shipped default attribute schemata for ArchiMate business-object and application-component
specializations, kept out of ``repo_default_schemata`` to hold that module within the
length policy. Merged into ``DEFAULT_SCHEMATA`` there, so the workspace template's ensure-missing
pass and the repository upgrade detector ship them identically.

Two single-source enums are defined ONCE here and referenced by every using schema. Both attach
via the existing convention: base ``attributes.<type>.schema.json`` and per-specialization
``attributes.<type>.<slug>.schema.json`` (resolved + merged by ``compute_effective_attribute_schema``).
Every schema is non-strict (``additionalProperties: true``) with ``required: []`` — the shipped set
is guidance, not a gate. Property keys follow the display-key (Title Case) convention.
"""

from __future__ import annotations

from src.domain.ontology_representation.attribute_scales import ORDINAL_SCALE, SCALE_KEYWORD

# Planner-friendly classification vocabulary; maps onto the TLP scale (documented in the
# Sensitivity description). Single-sourced so business-object and any future using schema agree.
SENSITIVITY_ENUM = ["Public", "Internal", "Confidential", "Strictly Confidential"]

# Portfolio lifecycle stage for a component/module/endpoint — distinct from a business object
# instance's own "Lifecycle States" list, which tracks an information item's states.
LIFECYCLE_STATE_ENUM = ["Planned", "In Development", "Active", "Deprecated", "Retired"]

# What this element emits and whether anyone is watching, in ascending order. Ranked, so a query
# can ask for "less observable than alerting".
#
# Deliberately a general property of the element, answerable by whoever built it without
# reference to any analysis: does it emit, and is someone looking. It is NOT "is this failure
# observable" — that is a verdict an analysis reaches, and asking an architect to tick it would
# turn a conclusion into an input. Emitting logs does not mean a particular silent failure gets
# noticed, so this informs whoever writes a detection control; it never stands in for one.
TELEMETRY_ENUM = ["None", "Logs", "Metrics and Logs", "Alerting", "Synthetic Probing"]

_SENSITIVITY_DESCRIPTION = (
    "Planner-friendly sensitivity of the object's content. Maps to TLP: Public→WHITE, "
    "Internal→GREEN, Confidential→AMBER, Strictly Confidential→RED."
)
_LIFECYCLE_STATE_DESCRIPTION = "Portfolio lifecycle stage of this component."
_TELEMETRY_DESCRIPTION = (
    "What this element emits and whether anyone is watching: None, Logs, Metrics and Logs, "
    "Alerting, or Synthetic Probing. A general property of the element, not a judgement about "
    "any particular failure."
)
_SOURCE_REPO_DESCRIPTION = (
    "Where the code lives. Informative only — declared as format: uri, but the validator runs no "
    "format checker, so any string is accepted."
)


def _str_list(description: str) -> dict:
    return {"type": "array", "items": {"type": "string"}, "description": description}


def _telemetry_property() -> dict:
    return {
        "type": "string",
        "enum": TELEMETRY_ENUM,
        SCALE_KEYWORD: ORDINAL_SCALE,
        "description": _TELEMETRY_DESCRIPTION,
    }


def _telemetry_only_schema(type_slug: str, title: str, subject: str) -> dict:
    """A base schema whose only shipped attribute is Telemetry.

    Base and per-specialization schemas are merged when the effective schema is computed, so a
    base carrying one attribute adds it to every specialization of that type without disturbing
    what those specializations declare.
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"attributes.{type_slug}.schema.json",
        "title": title,
        "description": f"Attribute schema for Properties table in {subject} entities.",
        "type": "object",
        "required": [],
        "properties": {"Telemetry": _telemetry_property()},
        "additionalProperties": True,
    }


ARCHIMATE_ATTRIBUTE_SCHEMATA: dict[str, dict] = {
    "attributes.business-object.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.business-object.schema.json",
        "title": "Business Object Attribute Schema",
        "description": "Attribute schema for Properties table in Business Object entities.",
        "type": "object",
        "required": [],
        "properties": {
            "Meaning": {"type": "string", "description": "What the object means to stakeholders."},
            "Provenance": {"type": "string", "description": "Where the content originates."},
            "Contained Information": _str_list("Information items the object carries."),
            "Internal Consistency Criteria": _str_list("Criteria that must hold within one instance."),
            "External Consistency Criteria": _str_list("Criteria against other objects or systems."),
            "Sensitivity": {"type": "string", "enum": SENSITIVITY_ENUM, "description": _SENSITIVITY_DESCRIPTION},
            "Lifecycle States": _str_list(
                "States an information-object INSTANCE passes through — distinct from the "
                "component-level 'Lifecycle State' enum."
            ),
        },
        "additionalProperties": True,
    },
    "attributes.data-object.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.data-object.schema.json",
        "title": "Data Object Attribute Schema",
        "description": "Attribute schema for Properties table in Data Object entities.",
        "type": "object",
        "required": [],
        "properties": {
            "Provenance": {"type": "string", "description": "Where the data originates."},
            # Reused (not AI-specific): an AI dataset's classification / sensitiveData in the
            # AIBOM derive from this, exactly as business-object Sensitivity does.
            "Sensitivity": {"type": "string", "enum": SENSITIVITY_ENUM, "description": _SENSITIVITY_DESCRIPTION},
        },
        "additionalProperties": True,
    },
    "attributes.application-component.service.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.application-component.service.schema.json",
        "title": "Application Component (Service) Attribute Schema",
        "description": "Attributes for a 'service' application component: a deployable service.",
        "type": "object",
        "required": [],
        "properties": {
            "Programming Languages & Versions": _str_list("One entry per language, including version."),
            "Frameworks & Versions": _str_list("One entry per framework, including version."),
            "Runtime Environments": _str_list("One entry per runtime environment."),
            "Communication Protocols & Versions": _str_list("One entry per protocol, including version."),
            "Owner": {"type": "string", "description": "Responsible party for the service."},
            "Source Repository": {"type": "string", "format": "uri", "description": _SOURCE_REPO_DESCRIPTION},
            "Lifecycle State": {
                "type": "string", "enum": LIFECYCLE_STATE_ENUM, "description": _LIFECYCLE_STATE_DESCRIPTION,
            },
        },
        "additionalProperties": True,
    },
    "attributes.application-component.module.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.application-component.module.schema.json",
        "title": "Application Component (Module) Attribute Schema",
        "description": "Attributes for a 'module' application component: an internal code module.",
        "type": "object",
        "required": [],
        "properties": {
            "Problem Domain": {"type": "string", "description": "The domain this module addresses."},
            "Lifecycle State": {
                "type": "string", "enum": LIFECYCLE_STATE_ENUM, "description": _LIFECYCLE_STATE_DESCRIPTION,
            },
        },
        "additionalProperties": True,
    },
    "attributes.application-component.endpoint.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.application-component.endpoint.schema.json",
        "title": "Application Component (Endpoint) Attribute Schema",
        "description": "Attributes for an 'endpoint' application component: an exposed access point.",
        "type": "object",
        "required": [],
        "properties": {
            "Communication Protocol & Version": {
                "type": "string", "description": "e.g. 'HTTP/1.1 + SSE'.",
            },
            "Authentication Method": {"type": "string", "description": "How access is guarded."},
            "Lifecycle State": {
                "type": "string", "enum": LIFECYCLE_STATE_ENUM, "description": _LIFECYCLE_STATE_DESCRIPTION,
            },
        },
        "additionalProperties": True,
    },
    # Telemetry is declared on the element kinds that can actually emit it — things that run.
    # Nothing else is added here: classification already lives on the data an element touches
    # (business-object / data-object Sensitivity), reachable through the model, so a component
    # declares no classification of its own.
    "attributes.application-component.schema.json": _telemetry_only_schema(
        "application-component", "Application Component Attribute Schema", "Application Component",
    ),
    "attributes.service.schema.json": _telemetry_only_schema(
        "service", "Service Attribute Schema", "Service",
    ),
    "attributes.technology-node.schema.json": _telemetry_only_schema(
        "technology-node", "Technology Node Attribute Schema", "Technology Node",
    ),
    "attributes.system-software.schema.json": _telemetry_only_schema(
        "system-software", "System Software Attribute Schema", "System Software",
    ),
}
