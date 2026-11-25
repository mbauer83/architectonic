"""The wire form of a candidate architecture's header and of the edits recorded among its operations.

One spelling for both surfaces: the REST request bodies are these models and the MCP tools take the
same models as arguments, so the two cannot come to accept different edits. What an edit means, and
the base it is recorded against, is `src.application.change_sets.recording`'s; nothing here decides
anything but which edit a request states. The field names an edit may name are the edit catalogue's
(`edit_field_catalogue`), quoted into the descriptions rather than restated as a second list.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.application.modeling.edit_field_catalogue import CONTENT, KEYED, creatable


def _named(names: frozenset[str]) -> str:
    return ", ".join(sorted(names))


_ENTITY_ID = "The entity, by its id in either spelling: `PREFIX@epoch.random` or with its slug."
_ENTITY_FIELD = f"The field changed: one of {_named(CONTENT['entity'])}."
_CONNECTION_FIELD = f"The field changed: one of {_named(CONTENT['connection'])}."
_KEY = (
    "For a field patched key by key (entity: "
    f"{_named(KEYED['entity'])}; connection: {_named(KEYED['connection'])}), the one key changed; "
    "omitted for any other field."
)
_VALUE = "What the field becomes. For a keyed field, null removes the key."


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateEntityEdit(_Closed):
    op: Literal["create_entity"]
    artifact_id: str | None = Field(
        None,
        description=(
            "The id the new entity is to have. Omit it and one is minted from the type and name and "
            "answered in the record; other edits then name the entity by that id."
        ),
    )
    fields: dict[str, JsonValue] = Field(
        description=(
            "What the entity states. Required: artifact_type, name, group (a model project's id or "
            f"slug). Accepted: {_named(creatable('entity'))}."
        ),
    )


class EditEntityEdit(_Closed):
    op: Literal["edit_entity"]
    artifact_id: str = Field(description=_ENTITY_ID)
    field: str = Field(description=_ENTITY_FIELD)
    value: JsonValue = Field(description=_VALUE)
    key: str | None = Field(None, description=_KEY)


class RemoveEntityEdit(_Closed):
    op: Literal["remove_entity"]
    artifact_id: str = Field(description=_ENTITY_ID)


class _Addressed(_Closed):
    source_entity: str = Field(description="The connection's source entity, by its id in either spelling.")
    connection_type: str = Field(description="The connection type, e.g. `archimate-serving`.")
    target_entity: str = Field(description="The connection's target entity, by its id in either spelling.")


class AddConnectionEdit(_Addressed):
    op: Literal["add_connection"]
    fields: dict[str, JsonValue] = Field(
        default_factory=dict, description=f"What the connection states. Accepted: {_named(creatable('connection'))}.",
    )


class EditConnectionEdit(_Addressed):
    op: Literal["edit_connection"]
    field: str = Field(description=_CONNECTION_FIELD)
    value: JsonValue = Field(description=_VALUE)
    key: str | None = Field(None, description=_KEY)


class RemoveConnectionEdit(_Addressed):
    op: Literal["remove_connection"]


class DropEdit(_Closed):
    """Take back what the candidate records about one thing, whatever it was."""

    op: Literal["drop"]
    artifact_id: str | None = Field(
        None, description="An entity: drops every operation about it, and for one the candidate creates, the create "
        "and every operation that names it.",
    )
    source_entity: str | None = Field(None, description="With connection_type and target_entity: a connection.")
    connection_type: str | None = None
    target_entity: str | None = None
    field: str | None = Field(None, description="Only the edit of this field (and `key`), not the whole thing.")
    key: str | None = None


#: One edit a candidate records among its operations. `drop` takes one back.
RecordedEdit = Annotated[
    CreateEntityEdit | EditEntityEdit | RemoveEntityEdit | AddConnectionEdit | EditConnectionEdit
    | RemoveConnectionEdit | DropEdit,
    Field(discriminator="op"),
]

CandidateState = Literal["draft", "candidate", "integrated", "rejected", "superseded"]


class CandidateHeader(_Closed):
    """A candidate as it is created: everything but its operations, which are recorded one edit at a time."""

    name: str = Field(min_length=1, description="What a reader tells it from its siblings by.")
    id: str | None = Field(
        None, description="Its id, when the caller chooses one (`CAND@epoch.random.slug`); minted if omitted.",
    )
    rationale: str | None = None
    state: Literal["draft", "candidate"] = Field(
        "draft", description="draft (operations may change) or candidate (offered for integration).",
    )
    parent: str | None = Field(None, description="The candidate it is read on top of, by id in either spelling.")
    scope: list[str] | None = Field(
        None,
        description="The model's entities it is read over without changing them. Omitted with `diagram`: the "
        "diagram's entities.",
    )
    diagram: str | None = Field(
        None,
        description="The stored diagram it is drawn on, by id. Where `scope` is omitted, the diagram's entities "
        "become the scope.",
    )
    answers: list[str] | None = Field(None, description="What it answers (end states), as references.")
    satisfies: list[str] | None = Field(None, description="What it satisfies (requirements), as references.")


class CandidatePatch(_Closed):
    """Header fields to change; the rest are kept. Operations change by recording edits, not here."""

    name: str | None = Field(None, min_length=1)
    rationale: str | None = None
    state: CandidateState | None = Field(
        None,
        description=(
            "draft <-> candidate; either -> rejected or superseded. integrated only by applying it; the "
            "three terminal states do not change."
        ),
    )
    parent: str | None = None
    scope: list[str] | None = None
    diagram: str | None = Field(
        None, description="The stored diagram it is drawn on; null draws it on what it stacks on.",
    )
    answers: list[str] | None = None
    satisfies: list[str] | None = None
    changes: dict[str, JsonValue] | None = Field(
        None,
        description=(
            "The operation list exactly as a read of this candidate answered it, to restore it (an undo). "
            "To change operations, record edits instead: they are given their bases by the server."
        ),
    )

    def stated(self) -> dict[str, Any]:
        """The fields the patch names, in the record's own keys."""
        return self.model_dump(exclude_unset=True)


class IntegrationResolution(_Closed):
    """One conflict between candidates being integrated, by kind and subject as the check reports it, and what is
    done about it. Applied in order, each over what the ones before left."""

    kind: Literal["same-key", "remove-versus-use"]
    subject: str = Field(min_length=1, description="The conflict's subject, as the integration answered it.")
    action: Literal["take", "drop", "merge"] = Field(
        description="`take` keeps `party`'s operation and drops the others'; `drop` drops `party`'s; `merge` writes "
        "`value` in place of the parties' values, where each sets the same field.",
    )
    party: str | None = Field(None, description="The candidate whose side is taken or whose operation is dropped.")
    value: JsonValue = Field(None, description="The merged value, for `merge`.")
