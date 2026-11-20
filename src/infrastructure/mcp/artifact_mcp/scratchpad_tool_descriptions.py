"""What each scratchpad tool tells an agent about itself.

Apart from the tools, as `edit_tool_descriptions` is for the edit tools: the sentences are the
contract an agent reads before it calls anything, they are long because the surface has rules worth
stating, and beside the registrations they had taken the module past the file-size limit.
"""

from __future__ import annotations

#: Said once and attached to every tool, because the shape is the whole contract here and an agent
#: that learns it from one tool should not have to rediscover it from the next.
_AGGREGATE_NOTE = (
    "\n\nThe resource is the whole scratchpad — there is no per-note or per-link operation, here or "
    "on REST. To change one thing use scratchpad_edit, which takes a delta; to write a document you "
    "already hold whole use scratchpad_replace. Both carry the `version` you read, and a stale one "
    "is refused rather than overwriting, because a scratchpad is a document someone else may have "
    "open."
)

LIST_DESCRIPTION = (
    "List scratchpads with their metadata — id, name, status, version, collection and note "
    "count, never the notes themselves. Filter by `group` (the collection it lives in) or "
    "`status`." + _AGGREGATE_NOTE
)

READ_DESCRIPTION = (
    "Read one scratchpad whole: its areas (the labelled frames), notes, links, groups and "
    "the layout block holding every coordinate. Each note reports the `area` containing it, "
    "which is derived from where it sits rather than stored. A note needs only a title — "
    "`destination`, `element-type` and the rest are optional at every moment. A link "
    "carries a `verdict` saying what the meta-ontology makes of it, and a note carries one "
    "when there is something to say: `narrowed` is a warning — the note is decided as "
    "something its area does not permit — and does not stop a lift; `refused` does. "
    "`classification-levels` lists the levels this scratchpad's meta-ontology refines a "
    "note through, in order, each with its `options`; a level's `source` says which note "
    "key holds its value (`hierarchy` is `domain`, `type` is `element-type`, "
    "`specializations` is `specialization`), and a note can be lifted once every "
    "`required` level is reached. A note's `attributes` are free until it reaches a level that "
    "`carries-attributes`; from there they are checked against the attribute schema of its type "
    "and specialization, as the properties of the entity it would become: a value the entity "
    "write would refuse is a `refused` verdict with the verifier's code, anything it would warn "
    "about is `narrowed`, and so is an attribute the schema does not declare."
    + _AGGREGATE_NOTE
)

CREATE_DESCRIPTION = (
    "Create a scratchpad. Only `name` is needed — `group` is the folder it sits in and defaults, "
    "because a scratchpad is free-standing and a lift chooses its target model-project PER FRAME. "
    "Seeded with four labelled frames — Vision & strategy, Portfolio, Project, Enabling — unless "
    "`seed_areas` is false. Nothing needs to be typed: a scratchpad exists to hold thinking before "
    "anything has been decided." + _AGGREGATE_NOTE
)

#: Said on both write tools, because it is where the value is supplied. The name invites "which
#: project does this land in", which is what `targets` answers — and that misreading, stored, made a
#: scratchpad unreadable in 0.4.0.
_DESTINATION_NOTE = (
    "\n\nA note's `destination` is what it BECOMES — one of `undecided`, `element`, `document`, "
    "`none`. It is not where it lands: the model-project a lift writes into is `targets` on "
    "scratchpad_lift, one per frame. Any other value is refused."
)

#: Said on both write tools, because both are compared with the stored scratchpad the same way.
_TRANSITION_NOTE = (
    "\n\nThe write is compared with the stored scratchpad, and refused for what it would make a "
    "note stop being: a note holding a `model-ref` keeps its type, specialization and destination "
    "(drop the `model-ref` in the same write to free it — that unbinds a bound note and forgets a "
    "realization); a `realized` note is not pointed at a different artifact; and the "
    "`meta-ontology` does not change while any stored note is typed."
)

REPLACE_DESCRIPTION = (
    "Replace a scratchpad whole. `scratchpad` is the document `scratchpad_read` returned, edited; "
    "`version` is the version you read it at. A mismatch is refused with `version_conflict` — "
    "reload and re-apply rather than retrying, or you will overwrite whatever moved.\n\n"
    "REMOVAL IS OMISSION: drop a note to delete it (its links go with it), drop a link to rub it "
    "out, and omit `element-type`, `domain`, `document-type` or `connection-type` — the key, not "
    "an empty string — to un-refine. Removal never retracts model content: deleting a `realized` "
    "note leaves the entity the lift created, and dropping `model-ref` is how a note stops "
    "claiming one.\n\n"
    "Invariants the aggregate enforces: every note has a title; a link's endpoints are notes of "
    "this scratchpad and not the same note; a group's members lie in one area and a note belongs "
    "to at most one group; the meta-ontology may not change while any note is typed. A violation "
    "is refused with the id at fault named." + _TRANSITION_NOTE + _DESTINATION_NOTE
)

EDIT_DESCRIPTION = (
    "Change a scratchpad by saying what changed, instead of sending the whole document back. Same "
    "write as scratchpad_replace, same invariants, same `version` and the same 409 on a stale one.\n\n"
    "`remove` is {collection: [id, ...]}, `upsert` is {collection: [patch, ...]}, over the "
    "collections `areas`, `notes`, `groups`, `links`. A patch is a MERGE PATCH identified by its "
    "`id`: a key you leave out keeps its stored value, a key set to null clears it, and an id the "
    "scratchpad does not have creates the row. `layout` is {collection: {id: [x, y] or [x, y, w, h], "
    "or null to unplace}}.\n\n"
    "Removing a note takes its links, its group memberships and its placement with it. Nothing here "
    "retracts model content: deleting a `realized` note leaves the entity the lift created, and "
    "clearing `model-ref` is how a note stops claiming one." + _TRANSITION_NOTE + _DESTINATION_NOTE
)

LIFT_DESCRIPTION = (
    "Lift a selection of notes — and the links among them — into ordinary model content, through "
    "the same verified write path as any other authoring. Plans unless `dry_run` is false.\n\n"
    "The answer reports four things per selection: what would be CREATED, what is SKIPPED because "
    "it already carries a model reference, what is REFUSED and why, and which links reach a note "
    "OUTSIDE the selection. A refusal blocks the whole lift — the write is one transaction. A note "
    "is refused while a classification level its meta-ontology requires is still open, and when "
    "one of its attributes holds a value the entity write would refuse; its `attributes` become "
    "the entity's properties, and its `body` the summary.\n\n"
    "A lift NEVER writes back to the model. A note already bound or realized is skipped, never "
    "updated: re-lifting would be bidirectional sync between a sketch and a governed model, and "
    "would clobber whatever was edited there since. A second lift therefore creates only what is "
    "new, which is usually the links between notes lifted before.\n\n"
    "`targets` maps a FRAME's id to the model-project its content lands in — one target per frame, "
    "because the frames are work archetypes and a canvas routinely holds work for more than one "
    "project. A frame with no entry lands in the root model. A project is created if it does not "
    "exist; one declaring a different meta-ontology is refused rather than coerced. "
    "`version` is the version you read the scratchpad at — a committed lift records what it "
    "created on the notes, so it is a write against that version.\n\n"
    "`draw` adds a layered ArchiMate view of what was lifted, with each of the scratchpad's GROUPS "
    "as a labelled box on it. Frames map to nothing — an area is a region of the workspace, not an "
    "element of a picture. The diagram is drawn AFTER the content commits, since it can only name "
    "entities that exist, so a diagram that fails does not retract the lift."
)

DELETE_DESCRIPTION = (
    "Delete a scratchpad and everything on it. Model content it lifted or bound is NOT touched: "
    "what a scratchpad put into the model is not the scratchpad's to retract."
)
