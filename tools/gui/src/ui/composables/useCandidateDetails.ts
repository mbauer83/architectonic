/**
 * *Edit details…* on a candidate's canvas (06·5): the element as the candidate composes it, and each field
 * the candidate holds differently from what it stacks on — its parent candidate, or the model — with the
 * value there. Read when the dialog opens, from the candidate compared with its parent, so the marks are
 * always against what it stands on, whatever base its reader is comparing with.
 */
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import { stableEntityId } from '../../domain/artifactId'
import { chosenIds } from '../../domain/candidates/candidateCanvas'
import type { DetailsSource } from '../components/canvasDetails'

export type CandidateDetailsAccess = Pick<ModelService, 'readCandidate' | 'compareCandidate' | 'listCandidates'>

/** What keeping an edit does on a candidate's canvas. */
export const CANDIDATE_DETAILS_NOTE =
  'Recorded in the candidate as you keep it; Undo takes it back. Nothing reaches the model before it is applied.'

export function useCandidateDetails(svc: CandidateDetailsAccess, candidateId: () => string): DetailsSource {
  const read = async (artifactId: string) => {
    const id = candidateId()
    const record = (await Effect.runPromise(svc.readCandidate(id))).record
    const parent = typeof record.parent === 'string' && record.parent ? record.parent : null
    const [compared, listed] = await Promise.all([
      Effect.runPromise(svc.compareCandidate(id, parent ?? 'model')),
      parent ? Effect.runPromise(svc.listCandidates()) : Promise.resolve([]),
    ])
    const chosen = chosenIds(compared.view)
    const isIt = (target: string) => stableEntityId(chosen.get(target) ?? target) === stableEntityId(artifactId)
    const fields = compared.view.entities.find((one) => isIt(one.id))?.fields ?? {}
    const changed = compared.diff.find((row) => typeof row.target === 'string' && isIt(row.target))
    return {
      fields,
      beneath: parent ? listed.find((one) => one.id === parent)?.name ?? parent : 'the model',
      differs: Object.entries(changed?.fields ?? {}).map(([field, value]) => ({ field, beneath: value.before })),
    }
  }
  return { note: CANDIDATE_DETAILS_NOTE, read }
}
