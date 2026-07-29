import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Effect } from 'effect'
import { useRoute, useRouter } from 'vue-router'
import type { DocumentList, DocumentType, GroupList } from '../../domain'
import type { ModelService } from '../../application/ModelService'
import type { RepoError } from '../../ports/ModelRepository'
import {
  LIST_TIERS,
  tierAllowsEngagementCollections,
  withTier,
  type TierSelection,
} from '../lib/tierUrlState'
import { documentListParams, savedGroupToMerge } from './listRequestParams'
import { useQuery } from './useQuery'
import { useTierFacet } from './useTierFacet'

const STORAGE_KEY = 'arch_group_document-collection'

/**
 * Documents list state: tier facet (URL-backed), type/title filters, and the
 * engagement collection. There is no first-visit redirect — with no group and no
 * saved preference the list loads at All/no collection; a saved preference merges
 * into the URL only when the tier allows engagement collections, and selecting
 * Enterprise clears the group (All does not implicitly restore it).
 */
export function useDocumentsListState(svc: ModelService) {
  const router = useRouter()
  const route = useRoute()
  const { tier } = useTierFacet(LIST_TIERS)

  const documentTypes = ref<DocumentType[]>([])
  const documentList = ref<DocumentList | null>(null)
  const groupsState = useQuery<GroupList, RepoError>()
  const loading = ref(false)
  const error = ref<string | null>(null)
  const docTypeFilter = ref('')
  const titleFilter = ref('')
  const showArchivedGroups = ref(false)

  const activeGroup = computed(() => (typeof route.query.group === 'string' ? route.query.group : ''))
  const collectionsAvailable = computed(() => tierAllowsEngagementCollections(tier.value))

  const setGroup = (group: string) => {
    const query = { ...route.query, group: group || undefined }
    void router.replace({ query, hash: route.hash })
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
    void router.push('/documents/groups')
  }

  const groupOptions = computed(() => {
    const all = documentList.value?.items ?? []
    const counts: Record<string, number> = {}
    for (const item of all) {
      const group = item.group ?? 'uncategorized'
      counts[group] = (counts[group] ?? 0) + 1
    }
    const registry = groupsState.data.value?.['document-collections'] ?? []
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

  const load = () => {
    loading.value = true
    error.value = null
    Promise.all([
      Effect.runPromise(svc.listDocumentTypes()),
      Effect.runPromise(svc.listDocuments(documentListParams(tier.value, docTypeFilter.value))),
    ]).then(([types, docs]) => {
      documentTypes.value = types
      documentList.value = docs
      loading.value = false
    }).catch((event: unknown) => {
      error.value = String(event)
      loading.value = false
    })
  }
  const loadGroups = () => groupsState.run(svc.listGroups('document-collection'))

  // The facet writes the URL; the derived tier updates reactively, then we refetch.
  watch(tier, () => { load() })

  let refreshEventSource: EventSource | null = null
  onMounted(() => {
    const saved = savedGroupToMerge(activeGroup.value, tier.value, localStorage.getItem(STORAGE_KEY))
    if (saved) {
      void router.replace({ query: { ...route.query, group: saved }, hash: route.hash })
    }
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

  const activeGroupTypeFilter = computed(
    () => groupOptions.value.find((group) => group.slug === activeGroup.value)?.type_filter ?? [],
  )

  const filteredItems = computed(() => {
    const needle = titleFilter.value.trim().toLowerCase()
    const items = documentList.value?.items ?? []
    return items.filter(
      (item) =>
        (!needle || item.title.toLowerCase().includes(needle)) &&
        (!activeGroup.value || (item.group ?? 'uncategorized') === activeGroup.value) &&
        (activeGroupTypeFilter.value.length === 0 || activeGroupTypeFilter.value.includes(item.doc_type)),
    )
  })

  return {
    tier, selectTier, collectionsAvailable,
    documentTypes, groupsState, loading, error,
    docTypeFilter, titleFilter, showArchivedGroups,
    activeGroup, setGroup, goToGroups,
    groupOptions, filteredItems, load, loadGroups,
  }
}
