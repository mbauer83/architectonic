/**
 * The candidate architectures page's list: every candidate (`useCandidates`), each one's scope and
 * operation count read off its record, and the catalogue grouped by scope and stack. A record that
 * cannot be read leaves its candidate listed without its facts.
 */
import { computed, shallowRef } from 'vue'
import { Effect } from 'effect'
import type { CandidateFacts } from '../../domain/candidates/candidateCatalog'
import { catalogOf, factsOf } from '../../domain/candidates/candidateCatalog'
import { type CandidateAccess, useCandidates } from './useCandidates'

export function useCandidateCatalog(svc: CandidateAccess) {
  const candidates = useCandidates(svc, { scopeDiagram: () => '' })
  const facts = shallowRef<ReadonlyMap<string, CandidateFacts>>(new Map())
  const groups = computed(() => catalogOf(candidates.all.value, facts.value))

  const readFacts = async (): Promise<void> => {
    const read = await Promise.all(candidates.all.value.map(async (one) => {
      const record = await Effect.runPromise(svc.readCandidate(one.id)).catch(() => null)
      return record ? [[one.id, factsOf(record.record)] as const] : []
    }))
    facts.value = new Map(read.flat())
  }

  /** List the candidates again, and read what each one's record says. */
  const refresh = async (): Promise<void> => {
    await candidates.load()
    await readFacts()
  }

  const create = async (record: Readonly<Record<string, unknown>>, diagram?: string): Promise<string | null> => {
    const id = await candidates.create(record, diagram)
    if (id) await readFacts()
    return id
  }

  const remove = async (id: string): Promise<boolean> => {
    const removed = await candidates.remove(id)
    if (removed) await readFacts()
    return removed
  }

  return { candidates, facts, groups, error: candidates.error, refresh, create, remove }
}

export type CandidateCatalog = ReturnType<typeof useCandidateCatalog>
