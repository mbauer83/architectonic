import type { Scratchpad } from '../../domain/schemas/scratchpads'
import { withAttribute } from './scratchpadAttributes'
import { withLevelValue, withoutLevelValue } from './scratchpadClassification'
import {
  withBody,
  withDocumentType,
  withLinkType,
  withReversedLink,
  withoutBinding,
  withoutLinkType,
  withoutRealization,
  withoutType,
} from './scratchpadEdits'

/** Apply one edit to the document being held, as one undoable step. */
export type Refine = (next: (current: Scratchpad) => Scratchpad) => void

/**
 * What each refinement the note panel asks for means as an edit of the document.
 *
 * The panel says what a person chose; which pure edit that is belongs beside the edits, not in the
 * view that happens to host the panel. Keyed by the panel's event names, so the view binds the
 * whole table with one `v-on` and a new refinement is one row here.
 */
export function notePanelEdits(refine: Refine) {
  return {
    'refine-note': (event: { id: string; levelId: string; value: string }) =>
      refine((current) => withLevelValue(current, event.id, event.levelId, event.value)),
    'unrefine-note': (event: { id: string; levelId: string }) =>
      refine((current) => withoutLevelValue(current, event.id, event.levelId)),
    'body-note': (event: { id: string; body: string }) =>
      refine((current) => withBody(current, event.id, event.body)),
    'attribute-note': (event: { id: string; name: string; value: unknown }) =>
      refine((current) => withAttribute(current, event.id, event.name, event.value)),
    'document-note': (event: { id: string; documentType: string }) =>
      refine((current) => withDocumentType(current, event.id, event.documentType)),
    // One gesture for both ways a note holds a type it can give up: its own, or a binding's.
    'untype-note': (event: { id: string }) =>
      refine((current) => withoutBinding(withoutType(current, event.id), event.id)),
    'forget-note': (event: { id: string }) =>
      refine((current) => withoutRealization(current, event.id)),
    'reverse-link': (event: { id: string }) =>
      refine((current) => withReversedLink(current, event.id)),
    'type-link': (event: { id: string; connectionType: string }) =>
      refine((current) => withLinkType(current, event.id, event.connectionType)),
    'untype-link': (event: { id: string }) =>
      refine((current) => withoutLinkType(current, event.id)),
  }
}
