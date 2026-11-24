/**
 * The candidate architectures page's list: every candidate (`useCandidates`), grouped by its root's
 * scope and stack. The list read carries each candidate's scope and operation count, so the page
 * makes one request however many candidates there are.
 */
import { computed } from 'vue'
import { catalogOf } from '../../domain/candidates/candidateCatalog'
import { type CandidateAccess, useCandidates } from './useCandidates'

export function useCandidateCatalog(svc: CandidateAccess) {
  const candidates = useCandidates(svc, { scopeDiagram: () => '' })
  const groups = computed(() => catalogOf(candidates.all.value))
  return {
    candidates, groups, error: candidates.error,
    refresh: candidates.load, create: candidates.create, remove: candidates.remove,
  }
}

export type CandidateCatalog = ReturnType<typeof useCandidateCatalog>
