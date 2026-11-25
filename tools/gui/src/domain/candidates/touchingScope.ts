/**
 * The open candidate architectures a scope about to be analysed touches (06·0): a candidate is open
 * while it is a draft or offered, and it touches the scope when what its stack is read over — its own
 * scope or one beneath it — shares an element with it. Listed so an analyst sees work already under way
 * on the same elements before starting another.
 */
import { stableEntityId } from '../artifactId'
import type { CandidateSummary } from '../schemas/candidates'

/** A candidate open on some of the scope, and how many of the scope's elements it reads. */
export interface TouchingCandidate {
  readonly candidate: CandidateSummary
  readonly shared: number
}

const OPEN: ReadonlySet<string> = new Set(['draft', 'candidate'])

/** The layers of *candidate*'s stack, top first, each once however its parents are linked. */
const layersOf = (candidate: CandidateSummary, byId: ReadonlyMap<string, CandidateSummary>): CandidateSummary[] => {
  const layers: CandidateSummary[] = []
  let layer: CandidateSummary | undefined = candidate
  while (layer && !layers.includes(layer)) {
    layers.push(layer)
    layer = layer.parent ? byId.get(layer.parent) : undefined
  }
  return layers
}

/** The open candidates whose stack reads any of *scope*, most shared first, then by name. */
export const touchingScope = (
  scope: readonly string[], candidates: readonly CandidateSummary[],
): readonly TouchingCandidate[] => {
  const wanted = new Set(scope.map(stableEntityId))
  const byId = new Map(candidates.map((one) => [one.id, one]))
  const sharedBy = (candidate: CandidateSummary): number =>
    new Set(layersOf(candidate, byId).flatMap((layer) => layer.scope.map(stableEntityId))
      .filter((id) => wanted.has(id))).size
  return candidates
    .filter((one) => OPEN.has(one.state))
    .map((candidate) => ({ candidate, shared: sharedBy(candidate) }))
    .filter((one) => one.shared > 0)
    .sort((a, b) => b.shared - a.shared || a.candidate.name.localeCompare(b.candidate.name))
}
