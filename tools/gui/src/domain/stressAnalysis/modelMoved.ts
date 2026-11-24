/**
 * "Model moved" (06·8): the operations of a candidate the model has moved under, read off the standing
 * the server serves with every comparison. Nothing here judges an operation; standing is the server's.
 *
 * *drifted*: what the operation replaces changed since it was written. Re-basing writes it again against
 * the model as it stands now. *conflicting*: it has nothing to apply to, so there is no base to re-read.
 */
import type { OperationStanding } from '../schemas/candidates'

export interface ModelMoved {
  readonly drifted: readonly OperationStanding[]
  readonly conflicting: readonly OperationStanding[]
}

export const modelMoved = (standing: readonly OperationStanding[]): ModelMoved => ({
  drifted: standing.filter((one) => one.standing === 'drifted'),
  conflicting: standing.filter((one) => one.standing === 'conflicting'),
})

export const hasMoved = (moved: ModelMoved): boolean => moved.drifted.length + moved.conflicting.length > 0

const operations = (count: number): string => `${count} operation${count === 1 ? '' : 's'}`

/** The band's sentence: how many operations moved, and what can be done about each kind. */
export const movedSentence = ({ drifted, conflicting }: ModelMoved): string => [
  drifted.length
    ? `${operations(drifted.length)} changed in the model since ${drifted.length === 1 ? 'it was' : 'they were'}`
      + ' written.'
    : '',
  conflicting.length
    ? `${operations(conflicting.length)} no longer ${conflicting.length === 1 ? 'has' : 'have'} anything to apply to.`
    : '',
].filter(Boolean).join(' ')
