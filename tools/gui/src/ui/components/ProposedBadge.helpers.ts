import { isProposed, type BaselineStanding } from '../../domain/schemas/baselineStanding'

/**
 * The badge's copy, from the standing itself.
 *
 * A tier badge names a place; this names a *difference*, so the label has to say which parts differ
 * or it repeats what a reader can already see. "Proposed: name, summary" is actionable; "Proposed"
 * alone sends them looking for the change.
 */
export const proposedLabel = (standing: BaselineStanding): string | null =>
  isProposed(standing) ? `Proposed: ${standing.changed_fields.join(', ')}` : null

/**
 * The full sentence a screen reader gets, including the condition when it is not `current`.
 *
 * `stale` and `conflicting` are the two states where the reader has to *do* something, so they are
 * the two that must not be conveyed by colour alone.
 */
export const proposedAriaLabel = (standing: BaselineStanding): string | null => {
  if (!isProposed(standing)) return null
  const fields = standing.changed_fields.join(', ')
  const count = standing.proposal_ids.length
  const changes = count === 1 ? 'one pending change' : `${count} pending changes`
  const condition = standing.condition === 'current' ? '' : `, ${standing.condition}`
  return `Not yet accepted upstream: ${changes} to ${fields}${condition}`
}

/** Which visual treatment the badge takes — a condition needing action is not the ordinary case. */
export const proposedVariant = (standing: BaselineStanding): 'pending' | 'attention' | null => {
  if (!isProposed(standing)) return null
  return standing.condition === 'current' ? 'pending' : 'attention'
}
