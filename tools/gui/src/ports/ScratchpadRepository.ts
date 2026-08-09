import type { Effect } from 'effect'
import type { Scratchpad, ScratchpadLift, ScratchpadList } from '../domain/schemas/scratchpads'
import type { RepoError } from './repositoryErrors'

/**
 * The scratchpad half of the outbound port.
 *
 * Its own file because `ModelRepository` reached the 350-line limit, and this is the seam that was
 * already there: six methods over one resource, answering one router and one set of MCP tools, and
 * the only part of the port whose resource is an aggregate rather than a record.
 */
export interface ScratchpadRepository {
  // Six, over one resource: the aggregate. No per-note method, because the canvas holds the whole
  // document in memory and saves it whole — which is what lets it debounce to one write a second
  // instead of one per drag.
  readonly listScratchpads: (
    params?: { group?: string; status?: string },
  ) => Effect.Effect<ScratchpadList, RepoError>
  readonly getScratchpad: (id: string) => Effect.Effect<Scratchpad, RepoError>
  readonly createScratchpad: (
    body: { name: string; group: string; description?: string },
  ) => Effect.Effect<Scratchpad, RepoError>
  // `version` is the one the client read. A mismatch is a 409 the caller resolves by reloading —
  // never an overwrite, since a scratchpad is a document someone else may have open.
  readonly replaceScratchpad: (
    id: string,
    body: { version: string; group: string; scratchpad: Record<string, unknown> },
  ) => Effect.Effect<Scratchpad, RepoError>
  readonly deleteScratchpad: (id: string) => Effect.Effect<void, RepoError>
  // The sixth is not a resource but an act, so it is the one scratchpad route whose final segment
  // names a verb. Preflight and execute share it: `dry-run` decides which, and a plan that had to
  // be re-fetched to be executed would be a plan made against a scratchpad that may have moved on.
  readonly liftScratchpad: (
    id: string,
    body: {
      version: string
      selection: string[]
      /** Frame id → the model-project its content lands in. One per frame, because the frames are
       * work archetypes and a canvas routinely holds work for more than one project. */
      targets?: Record<string, string>
      /** Draw a view of what was lifted. Second-order: created after the content commits, since it
       * can only name entities that exist, so a diagram that fails does not retract the lift. */
      draw?: boolean
      'dry-run'?: boolean
    },
  ) => Effect.Effect<ScratchpadLift, RepoError>
}
