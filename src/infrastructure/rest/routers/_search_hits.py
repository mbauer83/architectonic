"""One search hit, as the keyword search serialises it.

Its own module because `state.py` holds what a request handler reaches for — repositories, roots,
the write gate — and this is a mapping from a record kind to its display fields. It also has one arm
per record kind, so it grows whenever the index learns a new one, and it grew `state.py` past the
source-length policy doing exactly that.

A scratchpad and a scratchpad *note* are two arms, because they answer two questions: the pad is where
someone did their thinking, the note is a thought. A pad whose notes have all been lifted has no notes
left and is still the record that the thinking happened.

Mirrors `KeywordSearchHit` arm for arm: `name` and `artifact_type` are the *display* reading, not the
stored one, because a mixed result list has one column for each and a reader does not care which
record kind supplied it.
"""

from __future__ import annotations

from typing import Any

from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    ScratchpadNoteRecord,
    ScratchpadRecord,
    SearchHit,
)
from src.infrastructure.rest.routers.state import is_global


def search_hit_to_dict(h: SearchHit) -> dict[str, Any]:
    """Serialize a search hit, mapping each record kind to its proper display fields.

    Documents expose ``title``/``doc_type`` (not ``name``/``artifact_type``); diagrams
    carry ``diagram_type``. Connections are not independently navigable and are excluded
    from search upstream, but are serialized defensively here for completeness.
    """
    rec = h.record
    base: dict[str, Any] = {
        "score": h.score,
        "record_type": h.record_type,
        "artifact_id": rec.artifact_id,
        "status": rec.status,
        "path": str(rec.path),
        "last_updated": rec.last_updated,
    }
    match rec:
        case EntityRecord():
            entity = {
                **base,
                "name": rec.name,
                "artifact_type": rec.artifact_type,
                "domain": rec.domain,
                "subdomain": rec.subdomain,
                "is_global": is_global(rec.path),
            }
            if rec.host_diagram_id is not None:
                entity["host_diagram_id"] = rec.host_diagram_id
                entity["diagram_internal"] = True
            return entity
        case DiagramRecord():
            return {**base, "name": rec.name, "artifact_type": rec.artifact_type, "diagram_type": rec.diagram_type}
        case DocumentRecord():
            return {**base, "name": rec.title, "artifact_type": rec.doc_type}
        case ConnectionRecord():
            return {**base, "name": "", "artifact_type": rec.conn_type, "source": rec.source, "target": rec.target}
        case ScratchpadRecord():
            # `artifact_type` is **empty**, because a pad has no type distinct from its kind. Every
            # other row carries something about the artifact itself here — an entity's element type, a
            # document's doc type, a diagram's diagram type — and a pad's answer to "what type is it"
            # is "a scratchpad", which the kind column already says.
            #
            # It carried the pad's `meta_ontology` first, on the reasoning that this is the one typed
            # thing a pad declares about itself. That was wrong twice. It is a fact about which
            # ontology governs the pad rather than about what the pad is, so it answered a question
            # nobody asked; and the nav dropdown strips an `archimate-` prefix so entity types read
            # `business` rather than `archimate-business` — which turned `archimate-4` into the
            # single character **4** in the type column of every pad hit.
            return {
                **base,
                "name": rec.name,
                "artifact_type": "",
                "description": rec.description or None,
            }
        case ScratchpadNoteRecord():
            # `artifact_type` is the note's decided element type, or empty — which is the honest
            # answer for a thought nobody has typed yet, and the state the feature exists to allow.
            # The scratchpad is named as the container so a hit says where the thought lives.
            return {
                **base,
                "name": rec.title,
                "artifact_type": rec.element_type,
                "domain": rec.domain or None,
                "scratchpad_id": rec.scratchpad_id,
                "scratchpad_name": rec.scratchpad_name,
            }
