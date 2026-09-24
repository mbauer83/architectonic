"""What an author is told about icons on a diagram type that draws them: one statement for every surface."""

from __future__ import annotations

from src.application.icons.effective_icons import DISPLAY_ICONS_KEY, TYPE_ICONS_KEY
from src.domain.icons.icon_ref import IconStyle


def icon_authoring_guidance(styles: tuple[IconStyle, ...]) -> dict[str, object]:
    return {
        "styles": list(styles),
        "statements": {
            DISPLAY_ICONS_KEY: "diagram_entities.display_icons maps an instance id (an entity's id, or an "
            "occurrence or node id) to an icon reference",
            TYPE_ICONS_KEY: "diagram_entities.type_icons maps an entity type or specialization name to an "
            "icon reference, for every element of it on this diagram",
        },
        "reference": "an icon id (ICO@…), or {icon: <id>, style: <one of styles>}; without a style the "
        "icon's own default-style applies",
        "precedence": "the instance's own icon, then a specialization key, then the type key, then the "
        "specialization's default; an icon that does not apply to the element is passed over",
        "find": "artifact_query_icons(applicable_to=<entity id or type name>) lists the icons that may "
        "be shown there; artifact_create_icon adds one",
    }
