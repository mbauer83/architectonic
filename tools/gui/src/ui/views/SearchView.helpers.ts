/**
 * What a search result's type chip says, per record kind.
 *
 * Every kind fills `artifact_type` with something meaningful except a diagram, which fills it with
 * the constant `"diagram"` — its *kind*, not its type. So a result list showed `adr` and `spec` for
 * documents, `application-component` and `requirement` for entities, and one undifferentiated
 * `diagram` for a C4 deployment view, an activity walkthrough and an ArchiMate motivation view alike.
 *
 * The specific type was already on the wire: `diagram_type` travels beside `artifact_type` and the
 * view simply did not read it. So this is a display rule, not a contract change — which is why it is
 * a pure function tested on its own rather than a fetch.
 */

/** The kinds a hit may be, as the search contract declares them. */
export interface TypedHit {
  readonly record_type: string
  readonly artifact_type?: string | null
  readonly diagram_type?: string | null
}

/**
 * The type to show, or `null` where the kind genuinely has none.
 *
 * A diagram reads `diagram_type`; every other kind reads `artifact_type`, which is where its own
 * type already arrives. Null rather than a placeholder for an untyped scratchpad note: the view says
 * "untyped" in its own words, and inventing one here would put that wording in two places.
 */
export const hitTypeLabel = (hit: TypedHit): string | null => {
  const specific = hit.record_type === 'diagram' ? hit.diagram_type : hit.artifact_type
  const trimmed = (specific ?? '').trim()
  return trimmed === '' ? null : trimmed
}

/**
 * What kind of artifact this is, in the reader's words.
 *
 * Shown beside the type because the two answer different questions — *a diagram* against *a C4
 * deployment view* — and a list mixing four kinds has to say which is which. Unknown kinds pass
 * through unchanged rather than being mapped to a catch-all: a kind this build has not heard of is
 * better shown by its own name than hidden behind "artifact".
 */
const KIND_LABELS: Readonly<Record<string, string>> = {
  entity: 'entity',
  diagram: 'diagram',
  document: 'document',
  connection: 'relationship',
  'scratchpad-note': 'note',
  'assurance-node': 'assurance',
}

export const hitKindLabel = (recordType: string): string => KIND_LABELS[recordType] ?? recordType
