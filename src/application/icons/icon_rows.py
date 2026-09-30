"""An icon as the surfaces describe it: what a picker chooses by, never its picture.

One mapping for REST and MCP alike, so the two cannot come to describe an icon differently; each adds
what its own rows carry beside it (REST whether the icon is global, both how it stands). Where it is
used is the second mapping, from the one reading of the library's use.
"""

from __future__ import annotations

from src.application.icons.icon_usage import IconUsers
from src.domain.icons.icon_record import IconRecord


def icon_fields(icon: IconRecord) -> dict[str, object]:
    meta = icon.metadata
    return {
        "artifact_id": meta.artifact_id,
        "name": meta.name,
        "attribution": meta.attribution,
        "applies_to": meta.applies_to.as_list(),
        "default_style": meta.default_style,
        "tags": list(meta.tags),
        "status": meta.status,
        "source_format": meta.source_format,
        "width": meta.width,
        "height": meta.height,
        "render_digest": meta.render_digest,
    }


def usage_fields(users: IconUsers) -> dict[str, object]:
    return {
        "used_on": [{"artifact_id": d.artifact_id, "name": d.name} for d in users.named_diagrams],
        "default_for": list(users.specializations),
    }
