# Candidate architectures and arranging diagrams through the API

This page describes how an agent or a script works with candidate architectures, and how it arranges
and saves a diagram, through the MCP tools and the REST API. The GUI uses the same operations.

&nbsp;

## Candidate architectures

A candidate architecture is a named, proposed change to the model. It holds a list of operations:
create, edit and remove an entity; add, edit and remove a connection. It is read on top of the model,
and optionally on top of another candidate (its parent). Nothing it records reaches the model until it
is applied.

### Identity and versions

A candidate's id has the form `CAND@epoch.random.slug`. Every operation accepts the short form
`CAND@epoch.random` as well, and entity ids in the same way: an operation naming
`APP@1712870400.yNhgdh` and one naming `APP@1712870400.yNhgdh.module-catalog` address the same entity.
Operations and scopes store the short form.

Every read and every write answers the candidate's `version`. A write states the version it was made
over as `based_on`; a write over an older version is refused with 409, and the refusal names the
current version.

### States

| State | Operations may change | Moves to |
|---|---|---|
| `draft` | yes | `candidate`, `rejected`, `superseded` |
| `candidate` | no | `draft`, `rejected`, `superseded` |
| `integrated` | no | — (reached only by applying it) |
| `rejected`, `superseded` | no | — |

### The operations

| Task | MCP tool | REST |
|---|---|---|
| List | `change_set_list` | `GET /api/change-sets` |
| Read the record and version | `change_set_read` | `GET /api/change-sets/{id}` |
| Create, optionally drawn on and scoped by a diagram, and with edits | `change_set_create` | `POST /api/change-sets` |
| Record edits | `change_set_record` | `POST /api/change-sets/{id}/operations` |
| Change the header or the state | `change_set_edit` | `PATCH /api/change-sets/{id}` |
| How each operation stands against the model | `change_set_standing` | `GET /api/change-sets/{id}/standing` |
| Compare against the model, the naive or another candidate | `change_set_compare` | `GET /api/change-sets/{id}/diff` |
| Draw a scope no stored diagram draws, as a generated view | — | `POST /api/scope-drawings` |
| Save the generated view a candidate is drawn on as a diagram | `change_set_save_diagram` | `POST /api/change-sets/{id}/save-as-diagram` |
| Check candidates for conflicting claims | `change_set_check` | `POST /api/change-set-checks` |
| Integrate candidates into a new one, resolving conflicts | `change_set_integrate` | `POST /api/change-set-integrations` |
| Re-base drifted operations | `change_set_rebase` | `POST /api/change-sets/{id}/rebase` |
| Apply to the model | `change_set_apply` | `POST /api/change-sets/{id}/apply` |
| Delete | `change_set_delete` | `DELETE /api/change-sets/{id}` |
| Residuality in each analysis that judged it | `change_set_residuality` | `GET /api/change-sets/{id}/residuality` |

### Recording edits

An edit names what it changes and the value it asks for. The server reads the value it replaces from
the model and the candidates beneath, and records it as the operation's base; the caller never states
a base. Several edits are recorded in one call, in order, and either all of them are recorded or none.

```json
{"based_on": "2af7398b5ba0bf27", "operations": [
  {"op": "create_entity", "fields": {"artifact_type": "application-component",
                                     "name": "Catalog Cache", "group": "platform-core"}},
  {"op": "edit_entity", "artifact_id": "APP@1712870400.yNhgdh", "field": "name",
   "value": "Cached Module Catalog"},
  {"op": "drop", "artifact_id": "APP@1712870400.ca3vm7"}
]}
```

- A create that names no id is given one, minted from its type and name, and the answer shows it.
  Later edits name the new entity by that id.
- An edit of a field replaces an earlier edit of the same field. An edit back to the value beneath
  removes the operation.
- `drop` takes back what the candidate records about an entity or a connection, or, with `field`, about
  one field of it. Dropping an entity the candidate creates also drops every operation that names it.

### Standing, drift and applying

`standing` reports each operation as `applies`, `already-there`, `drifted` or `conflicting`, with a
sentence saying what to do. An operation has drifted when the value it replaces changed in the model
after it was recorded. `change_set_rebase` records each drifted operation again against the model as
it is now, keeping the value it asks for.

`change_set_apply` writes every operation in one transaction and marks the candidate `integrated`.
It is refused while an operation conflicts or has drifted, or while a candidate beneath it is not
integrated. Operations already in the model are skipped. A dry run, the default, answers what would be
written and the refusal, if any.

### Integrating

`change_set_integrate` makes a new draft candidate that holds the operations of two or more drafts or
offered candidates. The candidates stack on the same candidate, or all on the model, and the new one
stacks there too. Operations that ask for the same thing are kept once.

Where the candidates disagree, a dry run (the default) lists each conflict with its `kind`, `subject`,
parties and the actions it permits:

| Action | Effect |
|---|---|
| `take` | Keeps the operation of the named `party` and drops the other parties' operations on that subject. |
| `drop` | Drops the operation of the named `party`. Where two remaining parties still disagree, the conflict stays. |
| `merge` | Writes `value` in place of the parties' values. Offered where every party sets the same field. |

Resolutions are applied in the order given, each to the conflicts that remain after the ones before.
A resolution that names no remaining conflict is refused. An integration is written only when no
conflict remains. The chosen candidates are left as they are, and nothing reaches the model until the
integration is applied.

```json
{"candidates": ["CAND@1795540000.aaaaaa", "CAND@1795540000.bbbbbb"], "name": "Integration",
 "resolutions": [{"kind": "same-key", "subject": "name of SRV@1712870400.Uv9Wx9",
                  "action": "take", "party": "CAND@1795540000.bbbbbb"}],
 "dry_run": false}
```

### Deleting

A candidate is kept while anything refers to it: a candidate stacked on it, an analysis that starts
from it, a verdict or an adaptation that names it, or its own integration. The refusal names what to
remove first. A delete is a dry run unless `dry_run` is false, and accepts `based_on`.

&nbsp;

## Stress analyses

A stress analysis evaluates a proposed architecture: its naive candidate. `analysis_start`
(`POST /api/stress-analyses`) creates the naive candidate and the stress-analysis document in one
write. The naive candidate holds the scope and the stored diagram it is drawn on; the document names
the naive candidate and, optionally, a `context`: the environment the architecture is evaluated in
and the decision the evaluation informs. A document's title is unique within its type, so the start
page asks `GET /api/document-types/stress-analysis/free-title` for its default title: the proposed
title, or that title numbered `(2)`, `(3)` and so on where another analysis already has it.

The canvases of the workspace and of a candidate's page draw a candidate with its own changes on the
picture. An element it removes stays drawn as a faded dashed ghost. **Apply…** in the workspace lists what is left in the analysis, then shows the chosen
candidate's dry run before it is applied.

A candidate records the diagram it is drawn on as `diagram`. A candidate stacked on another is drawn
on the nearest diagram its stack names. Where none is named, as for a scope chosen by a search or by a
viewpoint that no stored diagram applies, a comparison is drawn on a view generated from the scope:
its elements and the relations among them. `change_set_save_diagram` stores that view as a new
diagram, through the same create as any diagram, and records it as the candidate's `diagram`, so the
candidate can be sketched on it. The diagram draws only what the model holds; what the candidate
creates or changes is drawn over it on the canvas and reaches the model only when the candidate is
applied. A candidate whose scope holds nothing of the model has no view to save. Stressors, end states, incidence, adaptations and verdicts are rows of the
document's tables, written with `artifact_edit_document_table`
(`PATCH /api/documents/{id}/tables/{table}`). The reads are `analysis_progress`, `analysis_incidence`
and `analysis_test_set`. Holding out a test set and reading residuality are described in
[Stress test set](stress-test-set.md).

&nbsp;

## Arranging and saving a diagram

| Task | MCP tool | REST |
|---|---|---|
| Layout keys, extents, the stored layout | `artifact_query_diagram_layout` | `GET /api/diagrams/{id}/layout/geometry` (with the drawings) |
| Change layout entries | `artifact_arrange_diagram` with `patch` | `PATCH /api/diagrams/{id}/layout` |
| Align, distribute, straighten, nest, group | `artifact_arrange_diagram` with `intents` | `POST /api/diagrams/{id}/layout/arrange` |
| Save the diagram whole, with model edits | `artifact_replace_diagram` | `PUT /api/diagrams/{id}` |

A layout patch names entries by section (`elements`, `boxes`, `relations`, `z`) and layout key. Each
entry is `null` to remove it, or `{value, based_on}`: what it becomes, and what it held when it was
read. When a `based_on` no longer holds, the whole patch is refused with 409 and nothing is written.

A whole save states the diagram's composition (type, name, entity and connection ids, diagram
entities, authored groupings), its layout as a whole block or as a patch, and model commands. The
commands create, rename, edit and delete elements and create and edit relations; an edit changes only
the fields it states. All of it is written in one write, or none of it. A second drawing of an
element is an `occurrence` item in the diagram entities:

```json
"diagram_entities": {"occurrence": [{"id": "renderer-again", "backing_entity_id": "APP@1777293136.yaxrWl"}]}
```

The occurrence id is then a layout key like an element's, and can be placed and given a z value.

A server that cannot run PlantUML answers 503 to the reads and writes that draw a diagram.

---

*Back to [Architecture modeling](index.md)*
