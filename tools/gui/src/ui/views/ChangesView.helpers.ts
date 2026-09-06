import type { ChangeSummary } from '../../domain/schemas/changes'
import { entityDetailRoute } from '../router/artifactRoutes'

/**
 * Where a change's subject is opened.
 *
 * Through the *reference*, and as an entity: a global artifact reference is an entity in this
 * repository whatever it stands for, so the entity route opens all three kinds. `kind` says which
 * vocabulary the change speaks, not where the reference lives.
 *
 * Null where there is no reference — the admin deployment reads the promoted artifact directly, and
 * offering a link to the enterprise id would be a link to something this repository does not hold.
 */
export const changeSubjectRoute = (change: ChangeSummary): string | null =>
  change.reference_id === null ? null : entityDetailRoute(change.reference_id)

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
