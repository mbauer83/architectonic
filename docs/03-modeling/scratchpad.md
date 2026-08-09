# Scratchpad

A scratchpad is somewhere to think **before anything is decided**. Notes with titles, links
between them, arranged on a canvas — no element types, no ontology, no naming a kind of thing
before you know what it is.

That last point is the reason it exists. Creating model content asks for a type first, and for a
newcomer — or for anyone at the start of a piece of work — that question arrives before there is an
answer to it. The scratchpad removes the question, and then lets the thinking that survives become
ordinary, verified model content through a **lift**.

Nothing on a scratchpad is model content until it is lifted. And a scratchpad **never writes back**:
what a lift put into the model is the model's, and a second lift creates only what is new. See the
[scratchpad-tier ADR](../architecture/decisions.md) for why bidirectional sync is excluded.

&nbsp;

## What is on one

| Part | What it is |
|---|---|
| **Note** | One thought. A **title is the only thing it must have** — body, type and the rest are optional at every moment. |
| **Link** | A drawn relation between two notes. Typed later, or never. |
| **Area** | A labelled frame on the canvas. A new scratchpad is seeded with four: Vision & strategy, Portfolio, Project, Enabling. |
| **Group** | A named cluster of notes inside one area — what becomes an authored grouping when a diagram is generated. |

The four frames are **work archetypes**, not layers. Only the first narrows what may go in it —
vision and strategy work is motivation and strategy by definition — while portfolio, project and
enabling work each reach across the whole model: a project produces application components and
business processes as readily as requirements, and narrowing those would invent a rule the work does
not have. A frame declares the **domains** it holds rather than a list of types, so the declaration
keeps meaning the same thing when the ontology gains one.

**Which area a note is in is decided by where it sits**, not by a field. Dragging a note into the
Portfolio frame *makes* it portfolio work; a note in no frame is `unfiled`, which is a legitimate
place to be, because thinking often starts in the margin. Where frames overlap, the smallest one
containing the note wins.

&nbsp;

## Working on the canvas

- **Double-click** empty canvas to create a note. It opens with the caret in its title.
- **Right-click** empty canvas for the rest of what can go there — a note, or an element the model
  already has. Whatever you choose lands at the point you clicked.
- **Drag** a note to move it. **Drag its right-hand handle** onto another note to link them.
- **Enter** commits a title, **Escape** abandons the edit.
- **Shift-click** a note to add it to the selection, or remove it — which is how a lift's selection
  is built. **Ctrl-click** does the same on Windows and Linux, **Cmd-click** on macOS, where
  Ctrl-click is the context-menu gesture and cannot mean two things at once.
- **Ctrl/Cmd+Z** undoes, **Ctrl/Cmd+Shift+Z** redoes. The history holds whole documents, so every
  kind of edit is reversible — creating, titling, moving, linking, deleting.
- **Scroll** to zoom about the pointer; drag the background to pan.

### Without a pointer

A canvas is the easiest surface in a product to build mouse-only and the least excusable one to
leave that way: this is the tier a newcomer is told to start on, so *start here* cannot mean *start
here if you can drag*. The notes layer is a real multi-select **listbox** — a screen reader announces
what is selected rather than leaving it to a border — and every gesture has a key:

| Key | On a focused note |
|---|---|
| **Tab** | move between notes |
| **Space** | add to the selection, or take it out |
| **Enter** / **F2** | put the caret in the title; **Escape** leaves it |
| **Delete** | delete the note (undoable, like every other edit) |
| **Menu key** / **Shift+F10** | open the canvas menu, anchored at that note |
| **Escape** | clear the selection |

Links render **dashed until they are typed**; once typed, they are drawn the way the ontology says
they are. `connections.yaml`'s `notation:` block is the single authority for arrow shape — line
style and the decoration at each end — and the canvas reads it rather than deciding for itself, so
a composition looks like a composition here, in the graph explorer, and on a rendered diagram.

**Click a link** to select and refine it. Its panel offers exactly the relations the ontology
permits for the pair as drawn, rather than the whole vocabulary, and leads with **Reverse the link**
when the reverse is the permitted one.

A note wears what it has decided: narrowing it to a **domain** colours the card, and choosing a
**type** adds that type's glyph — the same two mechanisms the entity list and the picker use, so a
note and the element it becomes look like the same thing on both sides of a lift. A note's **body**
becomes the entity's summary when it is lifted, which is why it is worth writing on the note rather
than afterwards.

&nbsp;

## Reaching for what already exists

**Right-click the canvas → Add existing element…** opens the same entity picker the rest of the
application uses, in place, and what you choose lands *at that point* as a **bound** note — one
that holds a one-way reference to model content that is already there.

The gesture is anchored to a point rather than to a frame on purpose. Area membership here is
spatial, so where you click is the decision; an affordance attached to the frame would have to
invent a placement rule, and would cost one control per frame for one capability. The search is
scoped to the element types that frame permits, so the permitted set does double duty — it filters
the type picker when narrowing, and scopes the search when pulling something in.

Binding is the move that makes a scratchpad useful against a repository that is not empty. Most
thinking touches things that exist — *this project realizes the capability we already have* — and
without binding, lifting would mint a duplicate with nothing to stop it.

A bound note takes its type **from the entity**, because the entity is the authority on what it is.
Two scratchpads may bind the same entity; strategy work and project work reference one capability
all the time. Within one scratchpad an entity binds once, since twice would draw one element as two
notes and lift them as one.

**Unbind** releases the reference and the borrowed type. The entity is untouched — a scratchpad
never retracts model content.

&nbsp;

## Narrowing a note, one level at a time

Nothing needs a type, ever. When you do know, the note panel narrows down the meta-ontology's own
[classification levels](../05-extensibility/ontology-modules.md#classification-levels) rather than
through a ladder this feature invented: domain, then entity type, then specialization for an
ontology that declares one.

Narrowing is reversible while nothing downstream depends on it. **Untyping** is free on a note that
is neither bound nor realized, and every link touching it reverts to unverified. A realized note is
**forgotten** instead — the reference is dropped and the entity stays exactly where it is. That is
what keeps the frozen meta-ontology from being a trap: forget the realizations, unbind the
bindings, untype the rest, and the scratchpad can change vocabulary again.

### What a link verdict says

Once both ends of a link are typed, the ontology has an opinion, and the panel renders it in five
words:

| Verdict | What it means |
|---|---|
| **unverified** | An end is undecided. Verification does not nag — this is a question nobody has answered yet. |
| **reference** | One end is a document. This becomes a one-way reference *from* the document *to* the model, so the direction you drew does not matter. |
| **permitted** | The ontology declares this triple. |
| **narrowed** | **W128/W129** — the relation exists, but a specialization on one end says it does not apply here. A warning; a lift proceeds. |
| **refused** | **E126** — the ontology declares no such relation between these types. A lift will not create it. |

A refusal leads with **Reverse the link** whenever the reverse *is* permitted. ArchiMate relations
are ordered triples, and dragging one the wrong way is the commonest slip there is — one click is
almost certainly what was meant. The permitted connection types for the pair follow as *did you mean
one of these*.

The verdict is decided on the server and served **with each link**. There is no verification
endpoint to call and no second implementation: the two tiers above are a consequence of what the
ontology declares about its own levels, and re-deciding them in the browser would put that split in
two places. Verdicts are never stored — an ontology may change under a saved scratchpad, and
persisting one would record an answer as though it were content.

### Saving

There is no save button, and there is no save-per-gesture either. The canvas holds the scratchpad in
memory, and writes **at most once a second**, after editing settles — plus immediately on navigating
away. A drag produces one save, not one save per pointer position: the endpoint sees a save and
never sees a drag, which is what keeps a canvas from putting thousands of small writes through a
path built for deliberate edits.

If someone else saved the same scratchpad since you loaded it, your save is **refused rather than
applied**, and the canvas says so. A scratchpad is a document two people may have open, and
last-write-wins would discard an afternoon of the other one's work silently.

&nbsp;

## Lifting into the model

**Right-click the canvas → Lift into the model…** turns a selection of notes — and the links among
them — into ordinary, verified model content, through the same write path as any other authoring.
Shift-click notes to build a selection; with none selected, the lift offers the whole scratchpad.

Nothing is written until you say so. The dialog shows the **preflight**, and it is the same plan the
execution runs rather than a client's guess at it:

| Group | What it means |
|---|---|
| **Will be created** | Each typed note becomes an entity; each typed, permitted link becomes a connection. |
| **Refused** | A note with no type, or a link the ontology declares no relation for (**E126**). |
| **Already in the model** | A bound or realized note, named by the artifact it already is. |
| **Warnings** | A narrowing (**W128/W129**). The relation exists, so the lift proceeds. |
| **Links reaching outside the selection** | One end in, one end out. Extend the selection, or accept that the link is not realized. |

**A refusal blocks the whole lift.** The write is one transaction — everything or nothing — and half
a lift is a state nobody asked for and nobody can name.

### Where it lands — one target per frame

The dialog asks once per frame the selection spans: an existing model-project, a **new one created
as part of the lift**, or blank for the root model. Per frame rather than per lift, because the
frames are work archetypes — vision and strategy work is cross-project by nature, project work
belongs to one project, enabling work is shared — so a canvas routinely holds work for more than one
of them, and one destination would turn the ordinary act into four lifts with the selection rebuilt
by hand each time. It costs nothing structurally: a lift spanning four projects is still one batch
and one transaction.

Per *note* would be the other extreme and is deliberately refused: the preflight would become a form
rather than a report, and the frame is already the grouping you can see.

A link crossing frames produces a connection whose ends sit in different projects, which the model
already supports — a connection lives with its source entity.

Creating the project here is deliberate — *"this thinking has become a project"* is the normal way a
project starts, and sending you away to make a group first would interrupt exactly the moment the
feature exists to serve. A target that declares a **different meta-ontology is refused, not
coerced**: content cannot land in a project whose vocabulary never declared it.

### Documents, and the references they record

A note may be destined for a **document** rather than an element — which is most of what portfolio
work actually produces: budgets, timelines, project outlines and lifecycle notes are prose and
figures, not ArchiMate elements. A note has one destination; choosing a document type drops the
element type rather than leaving both set.

A link touching a document is **not a connection**. No relation runs to a document, so it becomes a
one-way **reference from the document to the model**, recorded on the document as a relative link in
its `References` section. The direction you drew does not matter and is deliberately not preserved:
a reference held by the *model* would make the model depend on a commentary about it.

The reference is written *as part of* the document rather than beside it, so it cannot outlive a
failed document create and needs no second transaction to stay consistent. Two document notes linked
together produce nothing — documents relate to each other in prose, not in the model.

### A second lift creates only what is new

A lift is one-way and it is not a sync. A note that already carries a model reference is **skipped
and reported, never updated** — what a scratchpad put into the model is not the scratchpad's to
rewrite, and re-lifting would silently clobber whatever was edited there since.

What a second lift *does* create is the **links between notes lifted before**, which is the useful
repeat case: three elements lifted last week, a fourth relation drawn between two of them today.

A committed lift records what each note became, so the canvas can show it and the next lift can skip
it. Dropping that record is **forget** — the entity stays exactly where it is.

&nbsp;

## On disk

One YAML document per scratchpad, in the collection it belongs to:

```
scratchpads/<group-slug>/SCR@<epoch>.<key>.<slug>.scratchpad.yaml
```

It is a git-versioned file like every other artifact, and it is meant to be **read in a diff**. Two
properties carry that:

- **collections are written in stable id order**, so re-saving an unchanged scratchpad produces an
  unchanged file;
- **all geometry lives in one `layout:` block at the end**, snapped to a 5-px grid — so an afternoon
  of tidying and an afternoon of thinking land in different parts of the file, and a one-pixel
  jitter never becomes a commit.

```yaml
artifact-id: SCR@1786300000.a7Kd2p.q3-portfolio-thinking
artifact-type: scratchpad
name: Q3 portfolio thinking
version: 0.1.4
status: draft
meta-ontology: archimate-4

areas:
  - id: strategy
    label: Vision & strategy

notes:
  - id: n1
    title: Grow into mid-market
  - id: n2
    title: Self-serve onboarding

links:
  - id: l1
    source: n1
    target: n2

layout:                       # every coordinate, and nothing else
  areas: {strategy: [0, 0, 1200, 600]}
  notes: {n1: [40, 60], n2: [320, 60]}
```

&nbsp;

## Reaching one from an agent

Every capability is reachable by **MCP and by REST alike** — six of each, over one service. That is
a deliberate property of this feature rather than of the platform: the scratchpad is the
lowest-barrier surface, so a human-only version would make the one place newcomers start the one
place an agent cannot help.

| Capability | MCP tool | REST |
|---|---|---|
| List | `scratchpad_list` | `GET /api/scratchpads` |
| Read | `scratchpad_read` | `GET /api/scratchpads/{artifact_id}` |
| Create | `scratchpad_create` | `POST /api/scratchpads` |
| Replace | `scratchpad_replace` | `PUT /api/scratchpads/{artifact_id}` |
| Delete | `scratchpad_delete` | `DELETE /api/scratchpads/{artifact_id}` |
| Lift | `scratchpad_lift` | `POST /api/scratchpads/{artifact_id}/lift` |

**A scratchpad is read and written whole.** There is no per-note operation on either surface: the
aggregate enforces its own invariants, a partial update cannot be validated without loading all of
it anyway, and one shape removes the class of bug where two partial updates interleave into a state
neither writer intended. To change one thing: read it, edit the returned document, and pass it back
with the `version` you read.

The invariants a write is refused for, each naming the id at fault:

- every note has a title;
- a link's endpoints are notes of this scratchpad, and not the same note;
- a group's members lie in one area, and a note belongs to at most one group;
- the meta-ontology may not change while any note is typed.

&nbsp;

## What is not here yet

The canvas, binding, narrowing and lift are what ship today. Still to come, in order: **documents**
as a destination; **groups** becoming authored groupings on a generated diagram; and **focus mode**
with scratchpad notes in the search index, ranked below model content.
