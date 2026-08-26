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

// The type label moved to `ui/lib/searchNavigation`, beside the route rule, because the nav-bar
// dropdown needs the same answer and a second copy is how the two came to disagree: this one read
// `diagram_type` for a diagram and the dropdown stripped an `archimate-` prefix, so one of them was
// wrong about diagrams and the other rendered a scratchpad's `archimate-4` as `4`.
export { searchHitTypeLabel as hitTypeLabel } from '../lib/searchNavigation'
export type { TypedHit } from '../lib/searchNavigation'

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
  scratchpad: 'scratchpad',
  'scratchpad-note': 'note',
  'assurance-node': 'assurance',
}

export const hitKindLabel = (recordType: string): string => KIND_LABELS[recordType] ?? recordType
