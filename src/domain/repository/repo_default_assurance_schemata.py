"""Default assurance attribute schemata for repo scaffolding.

Split out of `repo_default_schemata.py` purely to stay under the source-length policy —
merged into `DEFAULT_SCHEMATA` there. Migrated off the dormant
`OntologyModule.attribute_profiles` surface, which had no live consumer besides these
scaffolding defaults.

Enum members come from the vocabulary modules that own them, never restated here: a scale
written out twice is a scale that will eventually differ in two places.
"""

from __future__ import annotations

from src.domain.assurance.assessment_scales import CONSEQUENCE_SEVERITY_SCALE, LIKELIHOOD_SCALE
from src.domain.assurance.classification import TLP_ORDER
from src.domain.assurance.constraint_dispositions import CONSTRAINT_DISPOSITION_SLUGS
from src.domain.assurance.failure_modes import (
    FAILURE_GUIDEWORD_SLUGS,
    PERSISTED_ASSESSMENT_STATES,
    RECORDED,
)
from src.domain.assurance.uca_guidewords import UCA_GUIDEWORD_SLUGS
from src.domain.ontology_representation.attribute_scales import ORDINAL_SCALE, SCALE_KEYWORD


def _ordinal_property(scale: tuple[str, ...]) -> dict[str, object]:
    """A string attribute whose enum is ranked, ascending."""
    return {"type": "string", "enum": list(scale), SCALE_KEYWORD: ORDINAL_SCALE}


def _consequence_severity_property() -> dict[str, object]:
    return _ordinal_property(CONSEQUENCE_SEVERITY_SCALE)


def _likelihood_property() -> dict[str, object]:
    return _ordinal_property(LIKELIHOOD_SCALE)


def _tlp_property(default: str | None = None) -> dict[str, object]:
    """A TLP level. Ranked so a query can ask for "more sensitive than", but note that the
    exposure decision itself is not schema-driven: `TLP_ORDER` stays its only authority."""
    declared = _ordinal_property(TLP_ORDER)
    if default is not None:
        declared["default"] = default
    return declared

_CONCERN_CLASSES = ["safety", "security", "operational", "financial", "privacy"]

ASSURANCE_ATTRIBUTE_SCHEMATA: dict[str, dict] = {
    "attributes.loss.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.loss.schema.json",
        "title": "Loss Attribute Schema",
        "description": "Attribute schema for Properties table in Loss entities.",
        "type": "object",
        "required": [],
        "properties": {
            # Severity is a property of the loss itself, so it lives here rather than on the
            # optional risk overlay — an analysis without a risk register still needs to know how
            # bad its losses are. The same scale rates a risk's impact: one quantity, one scale,
            # asked from two directions.
            "severity": _consequence_severity_property(),
            "tlp": _tlp_property(),
        },
        "additionalProperties": True,
    },
    "attributes.failure-mode.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.failure-mode.schema.json",
        "title": "Failure Mode Attribute Schema",
        "description": "Attribute schema for Properties table in Failure Mode entities.",
        "type": "object",
        "required": [],
        "properties": {
            "failure_type": {"type": "string", "enum": list(FAILURE_GUIDEWORD_SLUGS)},
            # The same distinction unsafe control actions already carry: predicted by analysis, or
            # seen to have happened. A design analysis and field data need telling apart, and a
            # second vocabulary for one distinction is how the two drift.
            "mode": {"type": "string", "enum": ["hypothesized", "observed"]},
            "concern_class": {"type": "string", "enum": _CONCERN_CLASSES},
            # Reused verbatim from control-structure nodes: the same three answers to "does this
            # point at an architecture entity yet".
            "binding_status": {
                "type": "string",
                "enum": ["bound", "unbound-pending", "out-of-scope"],
                "default": "unbound-pending",
            },
            "assessment_state": {
                "type": "string",
                "enum": list(PERSISTED_ASSESSMENT_STATES),
                "default": RECORDED,
            },
            "dismissed_by": {"type": "string"},
            "dismissal_rationale": {"type": "string"},
            "tlp": _tlp_property(),
        },
        "additionalProperties": True,
    },
    "attributes.assurance-constraint.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.assurance-constraint.schema.json",
        "title": "Assurance Constraint Attribute Schema",
        "description": "Attribute schema for Properties table in Assurance Constraint entities.",
        "type": "object",
        "required": [],
        "properties": {
            "concern_class": {"type": "string", "enum": _CONCERN_CLASSES},
            # Ranked strongest control first, so "dispositioned weaker than controlled with
            # evidence" is a query rather than an inspection. The order encodes preference among
            # controls, not magnitude.
            "disposition": _ordinal_property(CONSTRAINT_DISPOSITION_SLUGS),
            "level": {"type": "string", "enum": ["system", "controller", "technical"]},
            "tlp": _tlp_property(),
            # Free text by intent: the rule it serves asks how enforcement is achieved, which is
            # an argument rather than a state. Named for a state vocabulary, it went unused.
            "enforcement_justification": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "attributes.control-structure-node.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.control-structure-node.schema.json",
        "title": "Control Structure Node Attribute Schema",
        "description": "Attribute schema for Properties table in Control Structure Node entities.",
        "type": "object",
        "required": [],
        "properties": {
            "node_role": {
                "type": "string",
                "enum": ["controller", "controlled-process", "actuator", "sensor"],
            },
            "binding_status": {
                "type": "string",
                "enum": ["bound", "unbound-pending", "out-of-scope"],
                "default": "unbound-pending",
            },
            "granularity_note": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "attributes.hazard.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.hazard.schema.json",
        "title": "Hazard Attribute Schema",
        "description": "Attribute schema for Properties table in Hazard entities.",
        "type": "object",
        "required": [],
        "properties": {
            "concern_class": {"type": "string", "enum": _CONCERN_CLASSES},
            "tlp": _tlp_property(default="TLP:WHITE"),
            "classification_scheme": {"type": "string"},
            "classification_code": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "attributes.risk.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.risk.schema.json",
        "title": "Risk Attribute Schema",
        "description": "Attribute schema for Properties table in Risk entities.",
        "type": "object",
        "required": [],
        "properties": {
            "likelihood": _likelihood_property(),
            "impact": _consequence_severity_property(),
            "treatment": {"type": "string", "enum": ["mitigate", "transfer", "avoid", "accept"]},
            # The same two quantities, rated after treatment, so they carry the same scales. A
            # residual rating that could not be compared with the one it is residual to would
            # answer nothing.
            "residual_likelihood": _likelihood_property(),
            "residual_impact": _consequence_severity_property(),
            "review_date": {"type": "string", "format": "date"},
        },
        "additionalProperties": True,
    },
    "attributes.unsafe-control-action.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "attributes.unsafe-control-action.schema.json",
        "title": "Unsafe Control Action Attribute Schema",
        "description": "Attribute schema for Properties table in Unsafe Control Action entities.",
        "type": "object",
        "required": [],
        "properties": {
            "uca_type": {
                "type": "string",
                "enum": list(UCA_GUIDEWORD_SLUGS),
            },
            "mode": {"type": "string", "enum": ["hypothesized", "observed"]},
            "context": {"type": "string"},
            "concern_class": {"type": "string", "enum": _CONCERN_CLASSES},
        },
        "additionalProperties": True,
    },
}
