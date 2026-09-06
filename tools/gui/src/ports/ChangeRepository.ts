import type { Effect } from 'effect'
import type { ChangeDiscarded, ChangeList } from '../domain/schemas/changes'
import type { RepoError } from './repositoryErrors'

/**
 * The local changes this repository is holding: edits to artifacts it does not own.
 *
 * Its own port, like the admin, scratchpad and diagram-reading surfaces beside it. Two operations
 * about one concern — what have I changed, and take that back — kept where a reader looking for
 * them finds them together, rather than folded into the general model surface where they would sit
 * between documents and diagrams and belong to neither.
 */
export interface ChangeRepository {
  readonly listChanges: () => Effect.Effect<ChangeList, RepoError>
  /** The record is kept in a terminal state, so this answers rather than returning nothing. */
  readonly discardChange: (id: string) => Effect.Effect<ChangeDiscarded, RepoError>
}
