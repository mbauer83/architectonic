"""The arc42 document type: twelve sections, each declaring the model content it expects.

arc42 (https://arc42.org) is a template for software architecture documentation by Dr. Gernot
Starke and Dr. Peter Hruschka, published under CC BY-SA 4.0. What is reproduced here is the
*structure* — the twelve chapter titles and their order. Every section hint below is this
project's own prose about what the section asks a repository for, so no arc42 text is
redistributed. The attribution the licence asks for travels with the type: `attribution` is served
with the schema and shown on the create form, and `licenses/content.json` puts it in the generated
`THIRD-PARTY-NOTICES.md`.

Its own module because `repo_default_schemata.py` is at its file-length limit, and because this is
one template rather than the base set every repository needs.

What makes arc42 the first real consumer of the widened connection vocabulary: a section here has
to ask for a *diagram* of a type (§3 a system context, §7 a deployment view) and a *document* of a
type (§9 an ADR), which the entity-only pair could not say. Only §9 and §10 require anything —
arc42 is unambiguous that decisions belong in one and quality requirements in the other, and a
template that refuses everything else on the day it is created is a template nobody finishes.
"""

from __future__ import annotations

#: What the licence asks a redistributor to carry. Read by the document-type contract and by the
#: shipped-content inventory, so the two cannot drift.
ARC42_ATTRIBUTION = (
    "Section structure from arc42 (https://arc42.org) by Dr. Gernot Starke and Dr. Peter Hruschka, "
    "licensed CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). "
    "Section guidance text is this project's own."
)

ARC42_DOCUMENT_SCHEMA: dict = {
    "abbreviation": "SAD",
    "name": "arc42 Software Architecture Documentation",
    "subdirectory": "arc42",
    "attribution": ARC42_ATTRIBUTION,
    "frontmatter_schema": {
        "type": "object",
        "required": ["title", "status"],
        "properties": {
            "title": {"type": "string"},
            "status": {"type": "string", "enum": ["draft", "accepted", "rejected", "superseded"]},
            "system": {"type": "string", "title": "System documented"},
            "keywords": {"type": "array", "items": {"type": "string"}},
        },
    },
    "suggested_connections": ["@all", "doc:@all", "diagram:@all"],
    "sections": [
        {
            "name": "Introduction and Goals",
            "template": "What the system does, who it is for, and the goals it is measured against.\n",
            "suggested_connections": ["goal", "outcome", "stakeholder", "requirement"],
        },
        {
            "name": "Architecture Constraints",
            "template": "What is fixed before any decision is taken — technical, organisational, legal.\n",
            "suggested_connections": ["driver", "principle", "@motivation-element"],
        },
        {
            "name": "Context and Scope",
            "template": "The system's boundary, and who and what sits on the other side of it.\n",
            "suggested_connections": [
                "diagram:c4-system-context",
                "diagram:c4-system-landscape",
                "business-actor",
                "application-component",
            ],
        },
        {
            "name": "Solution Strategy",
            "template": "The few decisions that shape everything else, and why they were taken.\n",
            "suggested_connections": ["doc:adr", "principle", "course-of-action"],
        },
        {
            "name": "Building Block View",
            "template": "The static decomposition: what the system is made of, level by level.\n",
            "suggested_connections": [
                "diagram:c4-container",
                "diagram:c4-component",
                "application-component",
                "service",
            ],
        },
        {
            "name": "Runtime View",
            "template": "How the building blocks interact in the scenarios that matter.\n",
            "suggested_connections": ["diagram:sequence", "diagram:activity", "process", "function"],
        },
        {
            "name": "Deployment View",
            "template": "Where the building blocks run, and on what.\n",
            "suggested_connections": [
                "diagram:c4-deployment",
                "diagram:archimate-technology",
                "technology-node",
                "artifact",
            ],
        },
        {
            "name": "Cross-cutting Concepts",
            "template": "The rules that hold across building blocks rather than inside one.\n",
            "suggested_connections": ["doc:standard", "doc:spec", "principle"],
        },
        {
            "name": "Architecture Decisions",
            "template": "The decisions themselves, each linked to the record that states it.\n",
            "required_connections": ["doc:adr"],
        },
        {
            "name": "Quality Requirements",
            "template": "What good looks like, stated so it can be verified.\n",
            "required_connections": ["requirement"],
            "suggested_connections": ["goal", "value"],
        },
        {
            "name": "Risks and Technical Debt",
            "template": "What is known to be wrong or uncertain, and what it would cost.\n",
            "suggested_connections": ["assessment", "driver"],
        },
        {
            "name": "Glossary",
            "template": "The terms this documentation uses, and what each one means here.\n",
            "suggested_connections": ["meaning", "business-object"],
        },
    ],
}
