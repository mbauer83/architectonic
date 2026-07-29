"""Assurance document type definitions for engagement repository scaffolding."""

from __future__ import annotations

ASSURANCE_DOCUMENT_SCHEMAS: dict[str, dict] = {
    "stpa-analysis": {
        "abbreviation": "STPA",
        "name": "STPA Analysis",
        "frontmatter_schema": {
            "type": "object",
            "required": ["title", "status", "concern_class"],
            "properties": {
                "title": {"type": "string"},
                "status": {"type": "string", "enum": ["draft", "in-progress", "complete", "archived"]},
                "concern_class": {
                    "type": "string",
                    "enum": ["safety", "security", "privacy", "operational"],
                },
                "analysis_scope": {"type": "string"},
            },
        },
        "required_sections": [
            "Purpose and Scope",
            "Losses",
            "Hazards",
            "Control Structure",
            "Unsafe Control Actions",
            "Loss Scenarios",
            "Assurance Constraints",
            "References",
        ],
        "suggested_entity_type_connections": ["@all"],
    },
    "cast-investigation": {
        "abbreviation": "CAST",
        "name": "CAST Investigation",
        "frontmatter_schema": {
            "type": "object",
            "required": ["title", "status", "incident_date"],
            "properties": {
                "title": {"type": "string"},
                "status": {"type": "string", "enum": ["draft", "in-progress", "complete", "archived"]},
                "incident_date": {"type": "string"},
                "analysis_baseline_id": {"type": "string"},
            },
        },
        "required_sections": [
            "Incident Description",
            "Control Structure As-Existed",
            "Observed Control Flaws",
            "Causal Scenarios",
            "Corrective Actions",
            "Derived Constraints",
            "References",
        ],
        "suggested_entity_type_connections": ["@all"],
    },
    "risk-assessment": {
        "abbreviation": "RSKA",
        "name": "Risk Assessment",
        "frontmatter_schema": {
            "type": "object",
            "required": ["title", "status", "scope"],
            "properties": {
                "title": {"type": "string"},
                "status": {"type": "string", "enum": ["draft", "in-progress", "complete", "archived"]},
                "scope": {"type": "string"},
                "framework": {
                    "type": "string",
                    "enum": ["ISO31000", "ISO27001", "NIST-CSF", "other"],
                },
            },
        },
        "required_sections": [
            "Scope and Context",
            "Risk Identification",
            "Risk Analysis",
            "Risk Evaluation",
            "Risk Treatment",
            "Monitoring and Review",
            "References",
        ],
        "suggested_entity_type_connections": ["@all"],
    },
    "risk-treatment-plan": {
        "abbreviation": "RTP",
        "name": "Risk Treatment Plan",
        "frontmatter_schema": {
            "type": "object",
            "required": ["title", "status"],
            "properties": {
                "title": {"type": "string"},
                "status": {"type": "string", "enum": ["draft", "approved", "in-progress", "complete"]},
                "review_date": {"type": "string"},
                "owner": {"type": "string"},
            },
        },
        "required_sections": [
            "Summary",
            "Selected Treatments",
            "Implementation Plan",
            "Residual Risk",
            "Sign-off",
        ],
        "suggested_entity_type_connections": ["@all"],
    },
    "compliance-statement": {
        "abbreviation": "CMPL",
        "name": "Compliance Statement",
        "frontmatter_schema": {
            "type": "object",
            "required": ["title", "status", "framework"],
            "properties": {
                "title": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["draft", "in-progress", "complete", "submitted", "archived"],
                },
                "framework": {"type": "string"},
                "version": {"type": "string"},
                "assessment_date": {"type": "string"},
            },
        },
        "required_sections": [
            "Scope",
            "Applicable Obligations",
            "Control Coverage",
            "Evidence Summary",
            "Gaps and Exceptions",
            "Sign-off",
            "References",
        ],
        "suggested_entity_type_connections": ["@all"],
    },
    "assurance-case": {
        "abbreviation": "AC",
        "name": "Assurance Case",
        "frontmatter_schema": {
            "type": "object",
            "required": ["title", "status", "claim_type"],
            "properties": {
                "title": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["draft", "in-progress", "complete", "submitted", "archived"],
                },
                "claim_type": {
                    "type": "string",
                    "enum": ["safety", "security", "combined"],
                },
            },
        },
        "sections": [
            {"name": "Purpose and Scope"},
            {"name": "Safety/Security Claims"},
            {"name": "GSN Argument Structure"},
            {"name": "Evidence Summary", "suggested_entity_type_connections": ["@all"]},
            {"name": "Argument Completeness"},
            {"name": "Sign-off", "suggested_entity_type_connections": ["stakeholder"]},
            {"name": "References"},
        ],
    },
}
