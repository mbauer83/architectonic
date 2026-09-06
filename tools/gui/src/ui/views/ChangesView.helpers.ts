import type { ChangeSummary } from '../../domain/schemas/changes'
import {
  diagramDetailRoute,
  documentDetailRoute,
  entityDetailRoute,
} from '../router/artifactRoutes'

/**
 * Where a change's subject is opened: the promoted artifact itself, in its own kind's view.
 *
 * **Never the reference.** A global artifact reference is machinery — excluded from every list and
 * every search on purpose — and linking one put a page in front of readers that shows a proxy and a
 * description written for no one ("Engagement-repo proxy for promoted document …"). The artifact a
 * reader knows is the promoted one, which is what search returns and what they edited.
 */
export const changeSubjectRoute = (change: ChangeSummary): string => {
  switch (change.kind) {
    case 'document':
      return documentDetailRoute(change.target_id)
    case 'diagram':
      return diagramDetailRoute(change.target_id)
    case 'entity':
      return entityDetailRoute(change.target_id)
  }
}

/** What the change does, in the author's own terms rather than in file terms. */
export const changedFieldsLabel = (change: ChangeSummary): string => change.changed_fields.join(', ')

/**
 * The sentence explaining a standing that needs something done about it, or null when none does.
 *
 * `stale` and `conflicting` are the two where the author has to act, so neither is left to colour.
 */
export const conditionExplanation = (change: ChangeSummary): string | null => {
  switch (change.condition) {
    case 'current':
      return null
    case 'stale':
      return 'The enterprise artifact has moved since this was written.'
    case 'conflicting':
      return 'This change and the enterprise artifact disagree about the same content.'
  }
}

/**
 * What the state means for the author, which is not the same as what it is called.
 *
 * A draft has been put to nobody: taking it back costs nothing. A submitted change is under review,
 * so withdrawing it is visible to someone else — and saying so is the difference between an
 * informed click and a surprise.
 */
export const stateExplanation = (change: ChangeSummary): string =>
  change.state === 'draft'
    ? 'Not sent for review yet.'
    : 'Under review. Taking it back withdraws it from whoever is looking.'

/**
 * Whether a value is long enough that showing it whole would bury the row it belongs to.
 *
 * A field like `summary` covers the artifact's entire content section, so "what it says now" can be
 * several paragraphs — and a change replacing all of it with one line is exactly what an author
 * needs to see, at a size they can still scan. The threshold is a display decision, so it lives
 * here with the rest of them rather than in the template.
 */
export const isLongValue = (value: string | null): boolean => (value?.length ?? 0) > 240

/** The key that identifies one field of one change, for remembering which values are expanded. */
export const divergenceKey = (changeId: string, field: string): string => `${changeId}:${field}`
