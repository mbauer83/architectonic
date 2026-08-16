"""Shipped default JSON-Schema data for repo scaffolding (base doc-types + entity schemata).

Pure declarative method data (domain layer): consumed by the workspace template's
ensure-missing pass AND the repository upgrade detector, so both surfaces ship the
same defaults. Assurance doc-types are merged onto BASE_DOCUMENT_SCHEMAS by the
template; here we keep only the base set and the attribute/frontmatter schemata.
"""

from __future__ import annotations

from src.domain.repository.repo_default_arc42 import ARC42_DOCUMENT_SCHEMA
from src.domain.repository.repo_default_assurance_schemata import ASSURANCE_ATTRIBUTE_SCHEMATA
from src.domain.repository.repo_default_attribute_schemata import ARCHIMATE_ATTRIBUTE_SCHEMATA

BASE_DOCUMENT_SCHEMAS: dict[str, dict] = {
    "arc42": ARC42_DOCUMENT_SCHEMA,
    "adr": {
        "abbreviation": "ADR",
        "name": "Architecture Decision Record",
        "subdirectory": "adr",
        "frontmatter_schema": {
            "type": "object",
            "required": ["title", "status"],
            "properties": {
                "title": {"type": "string"},
                "status": {"type": "string", "enum": ["draft", "accepted", "rejected", "superseded"]},
                "deciders": {"type": "array", "items": {"type": "string"}},
                "date": {"type": "string"},
            },
        },
        "required_sections": ["Context", "Decision", "Consequences"],
        "section_templates": {
            "Context": "Describe the problem or situation requiring a decision.\n",
            "Decision": "Describe the decision that was made and why.\n",
            "Consequences": "Describe the resulting context, trade-offs, and any follow-up actions.\n",
        },
        "suggested_connections": ["@all"],
    },
    "spec": {
        "abbreviation": "SPC",
        "name": "Specification",
        "frontmatter_schema": {
            "type": "object",
            "required": ["title", "status"],
            "properties": {
                "title": {"type": "string"},
                "status": {"type": "string", "enum": ["draft", "accepted", "rejected", "superseded"]},
                "keywords": {"type": "array", "items": {"type": "string"}},
            },
        },
        "required_sections": ["Scope", "Summary", "Specification"],
        "section_templates": {
            "Scope": "State what this specification covers and any explicit exclusions.\n",
            "Summary": "Summarise the intent in 2-3 sentences.\n",
            "Specification": "Provide the detailed specification.\n",
        },
    },
    "standard": {
        "abbreviation": "STD",
        "name": "Standard",
        "frontmatter_schema": {
            "type": "object",
            "required": ["title", "status", "applies_to"],
            "properties": {
                "title": {"type": "string"},
                "status": {"type": "string", "enum": ["draft", "accepted", "rejected", "superseded"]},
                "applies_to": {"type": "array", "items": {"type": "string"}},
            },
        },
        "sections": [
            {
                "name": "Scope",
                "template": "State what this standard applies to and any explicit exclusions.\n",
            },
            {
                "name": "Motivation",
                "template": "Explain why this standard is needed.\n",
                "suggested_connections": ["principle", "goal"],
            },
            {
                "name": "Summary",
                "template": "Summarise the standard in 2-3 sentences.\n",
            },
            {
                "name": "Specification",
                "template": "Provide the normative specification with SHALL/SHOULD/MAY guidance.\n",
                "required_connections": ["requirement"],
            },
        ],
    },
}

DEFAULT_SCHEMATA: dict[str, dict] = {
    **ASSURANCE_ATTRIBUTE_SCHEMATA,
    **ARCHIMATE_ATTRIBUTE_SCHEMATA,
    "connection-metadata.archimate-influence.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "connection-metadata.archimate-influence.schema.json",
        "title": "Influence Relationship Properties",
        "description": "Optional presentation properties for ArchiMate influence relationships.",
        "type": "object",
        "required": [],
        "properties": {
            "polarity": {
                "type": "string",
                "title": "Polarity",
                "description": "Show whether the source has a positive or negative influence on the target.",
                "enum": ["positive", "negative"],
            },
        },
        "additionalProperties": True,
    },
    "attributes.capability.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.capability.schema.json",
        "title": "Capability Attribute Schema",
        "description": "Attribute schema for Properties table in Capability entities.",
        "type": "object",
        "required": ["Maturity"],
        "properties": {
            "Maturity": {
                "type": "string",
                "enum": ["Not Assessed", "Initial", "Developing", "Defined", "Managed", "Optimising"],
                "default": "Not Assessed",
            },
            "Realizes": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "attributes.driver.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.driver.schema.json",
        "title": "Driver Attribute Schema",
        "description": "Attribute schema for Properties table in Driver entities.",
        "type": "object",
        "required": ["Category"],
        "properties": {
            "Category": {
                "type": "string",
                "enum": [
                    "Unspecified",
                    "External Trend",
                    "Internal Challenge",
                    "Market Gap",
                    "Organizational",
                    "Organizational Constraint",
                    "Organizational Trend",
                    "Regulatory & Standards Trend",
                    "Technical Trend",
                    "Technological",
                    "Technology Trend",
                ],
                "default": "Unspecified",
            },
            "Source": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "attributes.goal.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.goal.schema.json",
        "title": "Goal Attribute Schema",
        "description": "Attribute schema for Properties table in Goal entities.",
        "type": "object",
        "required": [],
        "properties": {
            "Priority": {"type": "string", "enum": ["Must", "Should", "Could", "Won't"]},
            "Measurability": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "attributes.principle.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.principle.schema.json",
        "title": "Principle Attribute Schema",
        "description": "Attribute schema for Properties table in Principle entities.",
        "type": "object",
        "required": [],
        "properties": {
            "Priority": {"type": "string", "enum": ["Must", "Should", "Could", "Won't"]},
            "Rationale": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "attributes.requirement.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.requirement.schema.json",
        "title": "Requirement Attribute Schema",
        "description": "Attribute schema for Properties table in Requirement entities.",
        "type": "object",
        "required": [],
        "properties": {
            "Priority": {"type": "string", "enum": ["Must", "Should", "Could", "Won't", "Never"]},
            "Category": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "attributes.resource.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.resource.schema.json",
        "title": "Resource Attribute Schema",
        "description": "Attribute schema for Properties table in Resource entities.",
        "type": "object",
        "required": [],
        "properties": {
            "investment_level": {
                "type": "integer",
                "title": "Investment Level",
                "minimum": 1,
                "maximum": 5,
                "description": (
                    "Relative investment concentration on this strategic asset, used by the "
                    "shipped resource-map heat-map. Bands: 1 minimal upkeep · 2 sustaining · "
                    "3 steady investment · 4 growth focus · 5 primary focus."
                ),
            },
        },
        "additionalProperties": True,
    },
    "attributes.stakeholder.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.stakeholder.schema.json",
        "title": "Stakeholder Attribute Schema",
        "description": "Attribute schema for Properties table in Stakeholder entities.",
        "type": "object",
        "required": [],
        "properties": {
            "Category": {"type": "string"},
            "Concerns": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "frontmatter.diagram.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "frontmatter.diagram.schema.json",
        "title": "Diagram Frontmatter Schema",
        "description": "JSON Schema for diagram file frontmatter. Extends tool-required base fields.",
        "type": "object",
        "required": ["artifact-id", "artifact-type", "name", "diagram-type", "version", "status", "last-updated"],
        "properties": {
            "artifact-id": {"type": "string", "pattern": "^[A-Z]{2,6}@\\d+\\.[A-Za-z0-9_-]+\\..+$"},
            "artifact-type": {"type": "string", "enum": ["diagram"]},
            "name": {"type": "string", "minLength": 1},
            "diagram-type": {"type": "string"},
            "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
            "status": {"type": "string", "enum": ["draft", "active", "deprecated"]},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "last-updated": {"type": "string"},
            "viewpoint": {
                "type": "object",
                "required": ["slug", "version"],
                "properties": {
                    "slug": {"type": "string"},
                    "version": {"type": "integer"},
                    "enforcement_override": {"type": "string", "enum": ["off", "warn", "ghost"]},
                    "derivation_params": {"type": "object"},
                },
            },
        },
        "additionalProperties": True,
    },
    "frontmatter.entity.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "frontmatter.entity.schema.json",
        "title": "Entity Frontmatter Schema",
        "description": (
            "JSON Schema for entity file frontmatter. Extends the tool-required base fields; "
            "tool-required fields cannot be removed or overridden."
        ),
        "type": "object",
        "required": ["artifact-id", "artifact-type", "name", "version", "status", "last-updated"],
        "properties": {
            "artifact-id": {"type": "string", "pattern": "^[A-Z]{2,6}@\\d+\\.[A-Za-z0-9_-]+\\..+$"},
            "artifact-type": {"type": "string"},
            "name": {"type": "string", "minLength": 1},
            "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
            "status": {"type": "string", "enum": ["draft", "active", "deprecated"]},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "specialization": {"type": "string"},
            "last-updated": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "frontmatter.outgoing.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "frontmatter.outgoing.schema.json",
        "title": "Outgoing Connections File Frontmatter Schema",
        "description": "JSON Schema for .outgoing.md file frontmatter. Extends tool-required base fields.",
        "type": "object",
        "required": ["source-entity", "version", "status", "last-updated"],
        "properties": {
            "source-entity": {"type": "string", "pattern": "^[A-Z]{2,6}@\\d+\\.[A-Za-z0-9_-]+\\..+$"},
            "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
            "status": {"type": "string", "enum": ["draft", "active", "deprecated"]},
            "last-updated": {"type": "string"},
        },
        "additionalProperties": True,
    },
}
