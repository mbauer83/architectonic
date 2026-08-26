"""A diagram that draws a given thing — a source/target pair, or one entity.

Its own module because both contracts need it and one already imports the other: `contracts.diagrams`
reads shapes from `contracts.entities`, so declaring it in either and importing it from the other
closes a cycle. Nothing else about it is shared, which is why this file holds one class.

One class for one concept. The entity page's "drawn in diagrams" list was about to declare a second
with the same name and a different id field; the OpenAPI generator flagged it by qualifying both with
their module paths. What a reader needs is the same either way: a name to choose by, and enough about
the diagram to know what kind of statement the reference is.
"""

from __future__ import annotations

from src.infrastructure.rest.contracts.wire_shape import Closed


class DiagramReference(Closed):
    """One diagram that draws the thing asked about.

    ``diagram_type`` and ``status`` are served on both surfaces, not only the entity page: a caller
    warning about a rename benefits from them equally, because a draft diagram drawing the pair is a
    weaker objection than an active one.
    """

    artifact_id: str
    name: str
    diagram_type: str
    status: str
