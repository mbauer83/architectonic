"""Default stress-analysis document type. Subject and hit ids resolve in the naive candidate."""

STRESS_ANALYSIS_SCHEMA = {
    "abbreviation": "STRESS",
    "name": "Stress analysis",
    "subdirectory": "stress-analyses",
    "frontmatter_schema": {
        "type": "object",
        "required": ["title", "status"],
        "properties": {
            "title": {"type": "string"},
            "status": {"type": "string", "enum": ["draft", "accepted", "rejected", "superseded"]},
            "question": {"type": "string"},
            "naive-candidate": {"type": "string"},
            "scope-diagram": {"type": "string"},
        },
    },
    "sections": [
        {"name": "Naive Architecture", "suggested_connections": ["diagram:@all"]},
        {
            "name": "Stressors",
            "tables": [
                {
                    "name": "stressors",
                    "row_id": "S",
                    "columns": [
                        {"name": "stressor", "required": True},
                        {"name": "kind"},
                        {"name": "origin", "enum": ["drawn", "elicited", "model-prompted"]},
                        {"name": "plausible", "type": "boolean"},
                        {"name": "set", "enum": ["design", "test"], "required": True},
                        {"name": "end_state", "type": "row", "table": "end-states"},
                        {"name": "subject"},
                        {"name": "consequence"},
                    ],
                }
            ],
        },
        {
            "name": "End States",
            "tables": [
                {
                    "name": "end-states",
                    "row_id": "E",
                    "columns": [
                        {"name": "end_state", "required": True},
                        {"name": "required_behaviour", "type": "reference", "to": ["requirement"]},
                        {"name": "affects", "type": "reference", "to": ["driver", "goal", "stakeholder"], "many": True},
                        {"name": "no_change_reason"},
                    ],
                }
            ],
        },
        {
            "name": "Adaptations",
            "tables": [
                {
                    "name": "adaptations",
                    "row_id": "A",
                    "columns": [
                        {"name": "end_states", "type": "row", "table": "end-states", "many": True, "required": True},
                        {"name": "candidate_architecture", "required": True},
                        {"name": "integration", "enum": ["candidate", "integrated", "decided-out", "superseded"]},
                        {"name": "reasoning"},
                    ],
                }
            ],
        },
        {
            "name": "Incidence",
            "tables": [
                {
                    "name": "incidence",
                    "row_id": "I",
                    "columns": [
                        {"name": "stressor", "type": "row", "table": "stressors", "required": True},
                        {"name": "component", "required": True},
                        {"name": "note"},
                    ],
                }
            ],
        },
        {
            "name": "Test",
            "tables": [
                {
                    "name": "survival",
                    "row_id": "T",
                    "columns": [
                        {"name": "stressor", "type": "row", "table": "stressors", "required": True},
                        {"name": "naive_survives", "type": "boolean"},
                        {"name": "integrated_survives", "type": "boolean"},
                    ],
                }
            ],
        },
    ],
}
