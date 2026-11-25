"""The wire form of a diagram layout patch and of the arranging intents, for REST and MCP alike.

The envelope is typed here — which sections a patch has, what an entry is, which intents exist and what
each names — so a schema says it to a caller. What a placement, a route or a z value *is* stays the
layout block's reader's to decide (`src.domain.diagrams.layout`); an entry's value is passed through to
it, and its refusal is the answer. One spelling for both surfaces, as `document_part_wire` is.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LayoutEntryPatch(_Closed):
    """One entry of the layout: what it becomes, and what the caller read it as."""

    value: JsonValue = Field(
        description=(
            "What the entry becomes, null to remove it. elements and boxes: {x, y, w?, h?} in whole numbers; "
            "relations: {from: {side, at}, to: {side, at}, via: [[x, y], …], label: {at, dx, dy}}; z: an integer."
        ),
    )
    based_on: JsonValue = Field(
        None,
        description=(
            "What the entry held when it was read (null for absent). When stated and no longer true, the whole "
            "patch is refused (409) and nothing is written; omitted, the entry is written whatever it holds."
        ),
    )


_Section = dict[str, LayoutEntryPatch | None]
_SECTION = (
    "Entries by layout key (as the geometry read names them); null removes the entry without checking it."
)


class LayoutPatch(_Closed):
    """Entries of a diagram's layout block to change, by section and key; the others are kept."""

    elements: _Section | None = Field(None, description=f"Element placements. {_SECTION}")
    boxes: _Section | None = Field(None, description=f"Box placements (groupings, rule boxes). {_SECTION}")
    relations: _Section | None = Field(None, description=f"Relation routes. {_SECTION}")
    z: _Section | None = Field(None, description=f"Stacking order of elements and boxes. {_SECTION}")

    def stated(self) -> dict[str, dict[str, Any]]:
        """The patch as the layout reader takes it: the stated sections, each entry as stated."""
        sections: dict[str, dict[str, Any]] = {}
        for section in self.model_fields_set:
            entries = getattr(self, section)
            if entries is not None:
                sections[section] = {
                    key: None if entry is None else entry.model_dump(exclude_unset=True)
                    for key, entry in entries.items()
                }
        return sections


_KEYS = "Element keys, as the geometry read names them."


class Align(_Closed):
    intent: Literal["align"]
    keys: list[str] = Field(min_length=2, description=_KEYS)
    edge: Literal["left", "right", "top", "bottom", "centre_x", "centre_y"]


class Distribute(_Closed):
    intent: Literal["distribute"]
    keys: list[str] = Field(min_length=3, description=_KEYS)
    axis: Literal["x", "y"]


class Straighten(_Closed):
    intent: Literal["straighten"]
    relations: list[str] = Field(min_length=1, description="Relation keys, as the geometry read names them.")


class ReturnToAutomatic(_Closed):
    intent: Literal["return_to_automatic"]
    keys: list[str] | None = Field(None, description="Element keys; omitted, the whole layout returns to PlantUML's.")


class Nest(_Closed):
    intent: Literal["nest"]
    keys: list[str] = Field(min_length=1, description="What joins the grouping, leaving any other.")
    grouping: str = Field(description="A listed grouping's id (`g-…`).")


class Unnest(_Closed):
    intent: Literal["unnest"]
    keys: list[str] = Field(
        min_length=1, description="What leaves its grouping for the grouping's parent or the canvas.",
    )


class CreateGrouping(_Closed):
    intent: Literal["create_grouping"]
    label: str = Field(min_length=1)
    keys: list[str] = Field(description="Its members.")
    parent: str | None = Field(None, description="The grouping it nests in (`g-…`); the canvas when omitted.")


class DeleteGrouping(_Closed):
    intent: Literal["delete_grouping"]
    grouping: str = Field(description="The grouping (`g-…`); its members and subgroups go to its parent.")


#: What an editor means, applied in order. A grouping that selects its members by a rule gains or loses
#: none by listing.
ArrangeIntent = Annotated[
    Align | Distribute | Straighten | ReturnToAutomatic | Nest | Unnest | CreateGrouping | DeleteGrouping,
    Field(discriminator="intent"),
]

#: The intents a diagram composition (a canvas save) carries: moving members between groupings.
RegroupIntent = Annotated[Nest | Unnest, Field(discriminator="intent")]


def stated_intents(intents: list[Any]) -> list[dict[str, Any]]:
    """The intents as the domain's reader takes them."""
    return [intent.model_dump(exclude_unset=True) for intent in intents]
