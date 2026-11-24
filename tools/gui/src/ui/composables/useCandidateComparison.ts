/**
 * Several candidate architectures read side by side against one common base: each through its own
 * `useCandidates` reading, so each pane is the candidate page's own operations and canvas, over one
 * shared list. The base is the one asked for where every compared candidate shares it, else the
 * nearest they share (`commonBase`). Whether their operations conflict is asked of the server's
 * integration check, on request: it reads only candidates offered for integration, and says so.
 */
import { computed, ref, shallowRef } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type { CandidateSummary, IntegrationCheck } from '../../domain/schemas/candidates'
import { changedByOthers, commonBase, sharedBases } from '../../domain/candidates/candidateComparison'
import { formatEffectError } from '../lib/errors'
import { type CandidateAccess, type Candidates, useCandidates } from './useCandidates'

/** What a comparison is of, as its address states it. */
export interface ComparisonAddress {
  readonly ids: () => readonly string[]
  /** The base asked for; empty for the nearest one the compared candidates share. */
  readonly base: () => string
  readonly diagram: () => string
}

export type ComparisonAccess = CandidateAccess & Pick<ModelService, 'checkCandidates'>

export function useCandidateComparison(svc: ComparisonAccess, address: ComparisonAddress) {
  const all = shallowRef<readonly CandidateSummary[]>([])
  const readings = new Map<string, Candidates>()
  const readingOf = (id: string): Candidates => {
    const known = readings.get(id)
    if (known) return known
    const made = useCandidates(svc, { scopeDiagram: address.diagram, all })
    readings.set(id, made)
    return made
  }

  const ids = computed(() => address.ids())
  const known = computed(() => ids.value.filter((id) => all.value.some((one) => one.id === id)))
  const choices = computed(() => sharedBases(known.value, all.value))
  const base = computed(() => commonBase(known.value, all.value, address.base()))
  const panes = computed(() => known.value.map((id) => ({ id, reading: readingOf(id) })))
  const others = computed(() => changedByOthers(panes.value.map(({ id, reading }) =>
    ({ id, diff: reading.comparison.value?.diff ?? [] }))))
  const nameOf = (id: string): string => all.value.find((one) => one.id === id)?.name ?? id

  const checked = shallowRef<IntegrationCheck | null>(null)
  /** The check made of the candidates compared now; one made of others is not theirs. */
  const check = computed(() =>
    checked.value?.candidates.join('\n') === known.value.join('\n') ? checked.value : null)
  const checkError = ref<string | null>(null)
  const checking = ref(false)

  const error = ref<string | null>(null)
  const load = async (): Promise<void> => {
    try {
      all.value = await Effect.runPromise(svc.listCandidates())
      error.value = null
    } catch (failure) {
      error.value = formatEffectError(failure)
    }
  }

  /** Read every compared candidate against the common base. */
  const read = async (): Promise<void> => {
    checkError.value = null
    await Promise.all(panes.value.map(({ id, reading }) => reading.select(id, base.value)))
  }

  /** Ask the server where the compared candidates' operations overlap. */
  const runCheck = async (): Promise<void> => {
    checking.value = true
    try {
      checked.value = await Effect.runPromise(svc.checkCandidates(known.value))
      checkError.value = null
    } catch (failure) {
      checked.value = null
      checkError.value = formatEffectError(failure)
    } finally {
      checking.value = false
    }
  }

  return { all, error, known, choices, base, panes, others, nameOf, check, checkError, checking, load, read, runCheck }
}

export type CandidateComparisonReading = ReturnType<typeof useCandidateComparison>
