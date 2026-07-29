import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Effect } from 'effect'
import { useRoute, useRouter } from 'vue-router'
import type { DiagramList, DiagramSummary, DiagramTypeSummary, GroupList } from '../../domain'
import type { ModelService } from '../../application/ModelService'
import type { RepoError } from '../../ports/ModelRepository'
import {
  LIST_TIERS,
  tierAllowsEngagementCollections,
  withTier,
  type TierSelection,
} from '../lib/tierUrlState'
import { diagramListParams, savedGroupToMerge } from './listRequestParams'
import { useQuery } from './useQuery'
import { useTierFacet } from './useTierFacet'

const STORAGE_KEY = 'arch_group_diagram-collection'

const matchesFilter = (d: DiagramSummary, filterKey: string): boolean => {
  if (!filterKey) return true
  if (filterKey === 'archimate-all') return d.diagram_type === 'archimate' || d.diagram_type.startsWith('archimate-')
  if (filterKey === 'matrix') return d.diagram_type === 'matrix'
  if (filterKey === 'other') {
    return d.diagram_type !== 'matrix' && d.diagram_type !== 'archimate' && !d.diagram_type.startsWith('archimate-')
  }
  return d.diagram_type === filterKey
}

/**
 * Diagrams list state: tier facet (URL-backed), type filter, and the engagement
 * collection. Query writes MERGE `route.query` (owned keys: `type`, `group`,
 * `tier`) so adjacent filters and the hash survive. No first-visit redirect; a
 * saved collection preference merges into the URL only when the tier allows
 * engagement collections, and selecting Enterprise clears the group.
 */
export function useDiagramsListState(svc: ModelService) {
  const route = useRoute()
  const router = useRouter()
  const { tier } = useTierFacet(LIST_TIERS)
  const diagramsState = useQuery<DiagramList, RepoError>()
  const groupsState = useQuery<GroupList, RepoError>()
  const diagramKinds = ref<DiagramTypeSummary[]>([])
  const showArchivedGroups = ref(false)

  const selectedType = ref(typeof route.query.type === 'string' ? route.query.type : '')
  const activeGroup = computed(() => (typeof route.query.group === 'string' ? route.query.group : ''))
  const collectionsAvailable = computed(() => tierAllowsEngagementCollections(tier.value))

  const setGroup = (group: string) => {
    void router.replace({ query: { ...route.query, group: group || undefined }, hash: route.hash })
    localStorage.setItem(STORAGE_KEY, group)
  }

  const selectTier = (value: TierSelection) => {
    const query = withTier(route.query, value)
    if (!tierAllowsEngagementCollections(value)) delete query.group
    // Refetch happens in the tier watcher AFTER route.query (and the derived tier)
    // updates — calling load() here would fetch with the stale pre-navigation tier.
    void router.replace({ query, hash: route.hash })
  }

  const goToGroups = () => {
    localStorage.removeItem(STORAGE_KEY)
    void router.push('/diagrams/groups')
  }

  const load = () => {
    diagramsState.run(svc.listDiagrams(diagramListParams(tier.value)))
  }
  const loadGroups = () => groupsState.run(svc.listGroups('diagram-collection'))
  const loadDiagramTypes = () => {
    void Effect.runPromise(svc.listDiagramTypes())
      .then((kinds) => { diagramKinds.value = kinds })
      .catch(() => { diagramKinds.value = [] })
  }

  const groupOptions = computed(() => {
    const all = diagramsState.data.value?.items ?? []
    const counts: Record<string, number> = {}
    for (const item of all) {
      const group = item.group ?? 'uncategorized'
      counts[group] = (counts[group] ?? 0) + 1
    }
    const registry = groupsState.data.value?.['diagram-collections'] ?? []
    if (registry.length > 0) {
      // Whole-catalog member_count from the registry — the loaded list is group-filtered,
      // so counting it shows zero for every non-active group.
      return registry.map((group) => ({
        slug: group.slug, name: group.name, count: group.member_count ?? 0,
        archived: group.archived ?? false, type_filter: group.type_filter ?? [],
      }))
    }
    return Object.entries(counts)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([slug, count]) => ({ slug, name: slug, count, type_filter: [] as string[] }))
  })

  const activeGroupTypeFilter = computed(
    () => groupOptions.value.find((group) => group.slug === activeGroup.value)?.type_filter ?? [],
  )

  const filteredItems = computed(() => {
    const items = diagramsState.data.value?.items ?? []
    return items.filter(
      (d) =>
        matchesFilter(d, selectedType.value) &&
        (!activeGroup.value || (d.group ?? 'uncategorized') === activeGroup.value) &&
        (activeGroupTypeFilter.value.length === 0 || activeGroupTypeFilter.value.includes(d.diagram_type)),
    )
  })

  const selectType = (key: string) => {
    selectedType.value = key
    void router.replace({ query: { ...route.query, type: key || undefined }, hash: route.hash })
    load()
  }

  let refreshEventSource: EventSource | null = null
  onMounted(() => {
    const saved = savedGroupToMerge(activeGroup.value, tier.value, localStorage.getItem(STORAGE_KEY))
    if (saved) {
      void router.replace({ query: { ...route.query, group: saved }, hash: route.hash })
    }
    loadDiagramTypes()
    load()
    loadGroups()
    refreshEventSource = new EventSource('/api/events')
    refreshEventSource.addEventListener('artifact_write_completed', () => {
      load()
      loadGroups()
    })
  })
  onUnmounted(() => {
    refreshEventSource?.close()
  })
  watch(
    () => route.query.type,
    (value) => {
      selectedType.value = typeof value === 'string' ? value : ''
      load()
    },
  )
  // The facet writes the URL; the derived tier updates reactively, then we refetch.
  watch(tier, () => { load() })

  return {
    tier, selectTier, collectionsAvailable,
    diagramsState, groupsState, diagramKinds, showArchivedGroups,
    selectedType, activeGroup, setGroup, goToGroups,
    groupOptions, filteredItems, selectType, load, loadGroups,
  }
}
