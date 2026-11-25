"""Default stress-analysis document type. Subject and hit ids resolve in the naive candidate.

An analysis evaluates a proposed architecture, its naive candidate, which owns the scope and the
diagram it is drawn on. The document names that candidate and, optionally, the context the evaluation
is made in: the environment, and the decision it informs.

A stressor belongs to the design set, which the analysis is walked and adapted against, or to the test
set, held apart and judged at the end. A verdict names the architecture it was reached on: the naive
architecture, or a candidate by id.
"""

#: The document type an analysis is, the frontmatter key naming its naive candidate, and the one holding
#: the context the evaluation is made in.
STRESS_ANALYSIS = "stress-analysis"
NAIVE_CANDIDATE = "naive-candidate"
ANALYSIS_CONTEXT = "context"

#: The two sets a stressor belongs to.
DESIGN_SET = "design"
TEST_SET = "test"
#: How a verdict names the naive architecture; any other architecture is named by its candidate id.
NAIVE_ARCHITECTURE = "naive"
#: How a verdict names the integration when candidates were integrated apart, so no one of them holds it all.
INTEGRATION_ARCHITECTURE = "integration"
#: What an architecture does under a test stressor.
SURVIVES, DEGRADES, FAILS = "survives", "degrades", "fails"

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
            NAIVE_CANDIDATE: {"type": "string"},
            ANALYSIS_CONTEXT: {"type": "string"},
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
                        {"name": "set", "enum": [DESIGN_SET, TEST_SET], "required": True},
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
            "name": "Test Set",
            "tables": [
                {
                    "name": "survival",
                    "row_id": "T",
                    "columns": [
                        {"name": "stressor", "type": "row", "table": "stressors", "required": True},
                        {"name": "architecture", "required": True},
                        {"name": "verdict", "enum": [SURVIVES, DEGRADES, FAILS]},
                        {"name": "usable", "type": "boolean"},
                        {"name": "reasoning"},
                    ],
                }
            ],
        },
    ],
}
