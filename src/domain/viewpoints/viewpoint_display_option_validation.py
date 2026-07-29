"""Display-option validation for viewpoint presentations: the exploration layout
choice and the label-attribute override — both representation-gated, both validated at
save time so an unsupported or unknown option never reaches a renderer."""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot, issue, resolve_attribute_path
from src.domain.viewpoints.viewpoint_validation_issue import ViewpointValidationIssue
from src.domain.viewpoints.viewpoints import PresentationSpec, Representation

LABEL_ATTRIBUTE_OPTION = "label_attribute"
_LABEL_ATTRIBUTE_REPRESENTATIONS: frozenset[Representation] = frozenset({"exploration", "diagram"})

LAYOUT_OPTION = "layout"
_LAYOUT_REPRESENTATIONS: frozenset[Representation] = frozenset({"exploration"})
VALID_EXPLORATION_LAYOUTS: frozenset[str] = frozenset({"clusters", "radial", "force"})

COLOR_BY_OPTION = "color_by"
_COLOR_BY_REPRESENTATIONS: frozenset[Representation] = frozenset({"exploration"})
#: What an unstyled exploration node is filled by. Declared, never inferred: colouring is a
#: presentation decision, and deriving it from the query's shape means a definition changes
#: how it looks because of what it selects. Anchoring a query to take a parameter is a
#: reachability choice, not a request to recolour every node by hop distance.
VALID_EXPLORATION_FILLS: frozenset[str] = frozenset({"domain", "hop-distance"})


def validate_color_by_option(presentation: PresentationSpec, *, path: str) -> list[ViewpointValidationIssue]:
    if COLOR_BY_OPTION not in presentation.display_options:
        return []
    option_path = f"{path}/display_options/{COLOR_BY_OPTION}"
    if presentation.representation not in _COLOR_BY_REPRESENTATIONS:
        representation = presentation.representation
        message = f"display option {COLOR_BY_OPTION!r} is unsupported by representation {representation!r}"
        return [issue("error", "unsupported-display-option", option_path, message)]
    value = presentation.display_options[COLOR_BY_OPTION]
    if not isinstance(value, str) or value not in VALID_EXPLORATION_FILLS:
        fills = ", ".join(sorted(VALID_EXPLORATION_FILLS))
        return [issue("error", "unknown-color-by", option_path, f"color_by must be one of: {fills}")]
    return []

def validate_layout_option(presentation: PresentationSpec, *, path: str) -> list[ViewpointValidationIssue]:
    if LAYOUT_OPTION not in presentation.display_options:
        return []
    option_path = f"{path}/display_options/{LAYOUT_OPTION}"
    if presentation.representation not in _LAYOUT_REPRESENTATIONS:
        representation = presentation.representation
        message = f"display option {LAYOUT_OPTION!r} is unsupported by representation {representation!r}"
        return [issue("error", "unsupported-display-option", option_path, message)]
    value = presentation.display_options[LAYOUT_OPTION]
    if not isinstance(value, str) or value not in VALID_EXPLORATION_LAYOUTS:
        layouts = ", ".join(sorted(VALID_EXPLORATION_LAYOUTS))
        return [issue("error", "unknown-layout", option_path, f"layout must be one of: {layouts}")]
    return []


def validate_label_attribute(
    presentation: PresentationSpec, *, path: str, registries: RegistrySnapshot
) -> list[ViewpointValidationIssue]:
    if LABEL_ATTRIBUTE_OPTION not in presentation.display_options:
        return []
    option_path = f"{path}/display_options/{LABEL_ATTRIBUTE_OPTION}"
    if presentation.representation not in _LABEL_ATTRIBUTE_REPRESENTATIONS:
        representation = presentation.representation
        message = f"display option {LABEL_ATTRIBUTE_OPTION!r} is unsupported by representation {representation!r}"
        return [issue("error", "unsupported-display-option", option_path, message)]
    value = presentation.display_options[LABEL_ATTRIBUTE_OPTION]
    if not isinstance(value, str) or not value:
        return [issue("error", "unknown-attribute", option_path, "label_attribute must be an attribute path")]
    declared = resolve_attribute_path(value, context="entity", registries=registries)
    if declared is None and not value.startswith("derived."):
        return [issue("error", "unknown-attribute", option_path, f"unknown label attribute {value!r}")]
    return []


