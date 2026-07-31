# REST API

The backend serves a live, self-describing REST API. The interactive docs and the machine
contract are always available from a running backend:

- **`/docs`** — interactive Swagger UI (try requests, see schemas).
- **`/redoc`** — reference-style rendering of the same spec.
- **`/openapi.json`** — the OpenAPI 3 document, for generating clients or contract checks.

## Fidelity guarantee (modeling & querying surface)

The modeling and querying operations — entities, connections, diagrams, viewpoints,
documents, groups, and the taxonomy/guidance reads — are documented to a fixed standard,
enforced by a contract test (`tests/tools/test_openapi_modeling_query_contract.py`) so it
cannot silently regress:

- every operation carries a **tag** (grouping it by concept in `/docs`) and a **summary**;
- every operation documents its **200 response body** with a schema derived from a typed
  response model — never a bare untyped `200`;
- **write** operations declare the error contract they can return: `400` (validation),
  `403` (forbidden), `409` (conflict), `423` (write-gate retryable), plus FastAPI's
  automatic `422` for request-body validation;
- **id-lookup reads** declare `404`.

Response schemas come from the handlers' **typed response models**, not hand-written JSON —
the type is the contract, and FastAPI generates the schema from it. Models declare the
fields worth documenting and allow additional properties, so a response is documented
without its payload ever being filtered.

## Modification stamps and ordering

Every browsable artifact carries **`last_updated`**, the UTC instant it was last written
(`2026-07-24T09:15:00Z`), on list rows, detail reads, and search hits — entities, diagrams,
documents, and connections alike. It is `null` for an artifact with no stamp: one that lives
inside a diagram rather than in a file of its own, or one from a repository that predates the
field. Lexical order equals chronological order, so a client may sort on the raw string.

Ordering is resolved **server-side, over the whole filtered population, before the page slice** —
otherwise ordering page 1 of 10 would silently mean "the newest of these 50", not "the newest".

| Endpoint | `sort` accepts | `order` | Default |
|---|---|---|---|
| `/api/entities` | `name`, `type` (or `artifact_type`), `status`, `domain`, `last_updated` | `asc` \| `desc` | repository order |
| `/api/assurance/nodes` | `updated_at`, `created_at`, `name`, `node_type` | `asc` \| `desc` | `updated_at` `desc` |

An unrecognised `sort` field is **not an error**: the response falls back to the natural order, so
a bookmarked URL naming a column that no longer exists still returns a usable list. Records
missing the sorted field sort **last in both directions** — "unknown" is not "oldest".
(One exception: `/api/assurance/nodes` sorts blank fields first when ascending.)

Connection-count columns (in/sym/out/total) are deliberately absent from the allow-list: they are
computed after the page slice, so they can only be ordered within a page. The GUI marks that
column's ordering as page-scoped rather than implying it spans the repository.

For assurance nodes, ordering happens in the store **before** the TLP exposure filter runs.
Filtering preserves the relative order of what survives, so ordering can change neither which
nodes a reader sees nor the withheld count.

## Failure-mode endpoints

Two endpoints back the failure-mode matrix. Both are gated like every other assurance route: a
locked store returns the locked response, and exposure filtering runs before anything is assembled,
so a withheld node cannot influence a count or a priority a caller can see.

| Endpoint | Purpose |
|---|---|
| `GET /api/assurance/analyses/{analysis_id}/matrix` | The matrix of one FMEA analysis: candidate elements crossed with the failure guidewords. The analysis is required — a grid spanning two analyses is not a ranking of either. Asked of another method it answers `409 analysis_method_mismatch`. |
| `POST /api/assurance/nodes/{node_id}/factor-assessments` | Append one human judgement of one factor to a failure mode. POST, not PUT: it appends a revision rather than replacing a value. |

`GET` returns one object per candidate element carrying its cells, how many guidewords have been
answered, how many have not, and the element's worst Action Priority. Each cell reports its state
(recorded, not-credible, untouched), its Action Priority, each factor with the basis it came from,
whether an occurrence value is being asked for at all, and the single next action that would advance
it. **Rows are not sorted by priority**, and deliberately: the order is the candidate order — the
elements a control structure names first, then the ones the architecture graph nominates — so a
client can sort as it likes while the response order stays stable between calls.

A `PUT` **appends rather than replaces**. What is being set is *the current judgement*, and the
revision series behind it is how a reader sees that it changed; nothing is overwritten. The body
requires `node_id`, `factor`, `value`, `justification`, `author` and `basis_digest` — the last naming
the picture of the model the judgement was made against, so that when the model moves the judgement
can be recognised as stale and the derived value can take over again.

Ordinal values do not sort lexically. `major` precedes `minor` alphabetically and follows it by rank,
so any ordering over severity, occurrence, detectability or TLP is by declared rank — see
[Ranked attributes](viewpoints-schema.md#ranked-attributes-x-scale-ordinal). There is no server-side
`sort` parameter on either endpoint.

## Deferred (second pass)

The assurance/security, promotion, sync, admin, and events endpoints are documented to
FastAPI's defaults today; giving them the same fidelity is a planned follow-up.
Generating a typed client SDK from the now-faithful spec is possible once that lands.

---

*See also: [CLI & backend](cli-and-backend.md) · [Configuration](configuration.md)*
