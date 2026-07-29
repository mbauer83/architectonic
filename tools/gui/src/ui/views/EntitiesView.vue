<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import type { EntityList, EntityTaxonomy, GroupList, ModuleSummary } from '../../domain'
import type { RepoScope, RepoError } from '../../ports/ModelRepository'
import { modelServiceKey } from '../keys'
import { useQuery } from '../composables/useQuery'
import { usePagination } from '../composables/usePagination'
import { useTierFacet } from '../composables/useTierFacet'
import {
  LIST_TIERS,
  tierAllowsEngagementCollections,
  withTier,
  type TierSelection,
} from '../lib/tierUrlState'
import { entityListScope, savedGroupToMerge } from '../composables/listRequestParams'
import TierBadge from '../components/TierBadge.vue'
import TierFacet from '../components/TierFacet.vue'
import { tierFromIsGlobal } from '../components/TierBadge.helpers'
import EntitiesTreemap from '../components/EntitiesTreemap.vue'
import ArchimateTypeGlyph from '../components/ArchimateTypeGlyph.vue'
import EntityGroupNavTree from '../components/EntityGroupNavTree.vue'
import ViewpointTablePage from '../components/ViewpointTablePage.vue'
import DataTable from '../components/DataTable.vue'
import type { DataTableColumn, SortDirection } from '../components/DataTable.types'
import {
  friendlyEntityId,
  getEntityConnectionTotal,
  getDomainLabel,
} from '../lib/domains'
import { formatLastModified, lastModifiedTitle } from '../lib/lastModified'
import { filtersToEntityCriteriaMapping, isServerSortKey, sortEntityRows } from './EntitiesView.helpers'

type ViewMode = 'table' | 'treemap'

const PAGE_SIZE = 50
const STORAGE_KEY = 'arch_group_model-project'

const svc = inject(modelServiceKey)!
const route = useRoute()
const router = useRouter()
const entityListState = useQuery<EntityList, RepoError>()
const groupsState = useQuery<GroupList, RepoError>()
const taxonomyState = useQuery<EntityTaxonomy, RepoError>()
const modulesState = useQuery<readonly ModuleSummary[], RepoError>()

const { tier } = useTierFacet(LIST_TIERS)
const isGlobal = computed(() => tier.value === 'enterprise')

const activeDomain = computed(() => (route.query.domain as string | undefined) ?? '')
const activeGroup = computed(() => (route.query.group as string | undefined) ?? '')
const viewMode = computed<ViewMode>(() => route.query.view === 'treemap' ? 'treemap' : 'table')
const typeFilter = ref((route.query.type as string | undefined) ?? '')
const sortKey = ref<string | null>(null)
const sortDir = ref<SortDirection>('asc')
const showArchivedGroups = ref(false)

// Group view: any selected group, including the real empty "uncategorized" group.
// All group entities are loaded at once (limit 1000); domain/type filters are client-side.
// Non-group view: server-side domain+type filtering with PAGE_SIZE pagination.
const isGroupView = computed(() =>
  !isGlobal.value && Boolean(activeGroup.value)
)
const listScope = computed<RepoScope | undefined>(() => entityListScope(tier.value, isGroupView.value))

const { currentPage, pageCount, hasPrev, hasNext, goNext, goPrev, reset: resetPage, offset } =
  usePagination(computed(() => entityListState.data.value?.total ?? 0), PAGE_SIZE)

const replaceQuery = (patch: Record<string, string | undefined>) =>
  void router.replace({ query: { ...route.query, ...patch }, hash: route.hash })

const selectTier = (value: TierSelection) => {
  const query = withTier(route.query, value)
  if (!tierAllowsEngagementCollections(value)) delete query.group
  void router.replace({ query, hash: route.hash })
}

const setDomain = (domain: string) => replaceQuery({ domain: domain || undefined })
const setGroup = (group: string) => {
  replaceQuery({ group: group || undefined, domain: undefined })
  localStorage.setItem(STORAGE_KEY, group)
}
const goToGroups = () => { localStorage.removeItem(STORAGE_KEY); void router.push('/entities/groups') }
const setViewMode = (view: ViewMode) => replaceQuery({ view: view === 'table' ? undefined : view })

const saveFiltersAsViewpoint = () => {
  const mapping = filtersToEntityCriteriaMapping(activeDomain.value, typeFilter.value)
  void router.push({ path: '/viewpoints', query: { seedEntityCriteria: JSON.stringify(mapping) } })
}

// A native-field order is resolved by the server over the whole filtered population; ordering the
// 50 rows of one page client-side would read as if it had ordered all of them.
const serverOrder = computed(() => isServerSortKey(sortKey.value)
  ? { sort: sortKey.value ?? undefined, order: sortDir.value }
  : {})

// The order the currently-loaded rows were fetched with, so a sort change can tell whether it
// needs the server at all.
const loadedOrder = ref('')
const orderKey = () => `${serverOrder.value.sort ?? ''}:${serverOrder.value.order ?? ''}`

const loadCurrentPage = () => {
  loadedOrder.value = orderKey()
  return entityListState.run(
    isGroupView.value
      ? svc.listEntities({ scope: listScope.value, group: activeGroup.value, limit: 1000, ...serverOrder.value })
      : svc.listEntities({
          scope: listScope.value,
          domain: activeDomain.value || undefined,
          artifactType: typeFilter.value || undefined,
          limit: PAGE_SIZE,
          offset: offset.value,
          ...serverOrder.value,
        }),
  )
}

const load = () => { resetPage(); loadCurrentPage() }
const loadGroups = () => groupsState.run(svc.listGroups('model-project'))
const loadModules = () => modulesState.run(svc.listModules())
const loadTaxonomy = () => taxonomyState.run(
  svc.listEntityTaxonomy({ scope: listScope.value, group: activeGroup.value || undefined })
)

const goToNextPage = () => { goNext(); loadCurrentPage() }
const goToPrevPage = () => { goPrev(); loadCurrentPage() }

// ── Viewpoint-driven table execution ────────────────────────────────────────
// A `?viewpoint=` query switches this catalog view to ViewpointTablePage — the same
// table driven by a fixed viewpoint population instead of domain/group browsing.
const viewpointSlug = computed(() => (route.query.viewpoint as string | undefined) ?? null)

onMounted(() => {
  if (viewpointSlug.value) return
  const saved = savedGroupToMerge(activeGroup.value, tier.value, localStorage.getItem(STORAGE_KEY))
  if (saved) {
    void router.replace({ query: { ...route.query, group: saved }, hash: route.hash })
  }
  load()
  loadGroups()
  loadModules()
  loadTaxonomy()
})

watch(tier, () => { typeFilter.value = ''; loadTaxonomy(); load() })
watch(activeGroup, () => { loadTaxonomy(); load() })
watch(activeDomain, () => { typeFilter.value = '' })
watch([activeDomain, typeFilter], () => { if (!isGroupView.value) load() })

let refreshEventSource: EventSource | null = null
onMounted(() => {
  refreshEventSource = new EventSource('/api/events')
  refreshEventSource.addEventListener('artifact_write_completed', () => { load(); loadGroups(); loadTaxonomy() })
})
onUnmounted(() => { refreshEventSource?.close() })

const groupOptions = computed(() => {
  // Counts come from the registry's whole-catalog member_count — deriving them from the loaded
  // (group-filtered, paginated) list made every non-active group read zero until clicked.
  const registryData = groupsState.data.value?.['model-projects']
  if (!registryData) return []
  const result = registryData.map(g => ({
    slug: g.slug,
    name: g.name,
    count: g.member_count ?? 0,
    archived: g.archived ?? false,
    meta_ontology: g.meta_ontology ?? '',
  }))
  return [...result].sort((a, b) => {
    if (a.archived !== b.archived) return a.archived ? 1 : -1
    if (a.slug === 'uncategorized' && b.slug !== 'uncategorized') return 1
    if (b.slug === 'uncategorized' && a.slug !== 'uncategorized') return -1
    return a.name.localeCompare(b.name)
  })
})

const activeDomainCounts = computed((): Record<string, number> | undefined => {
  const tax = taxonomyState.data.value
  if (!tax) return undefined
  return Object.fromEntries(tax.domains.map(d => [d.name, d.count]))
})

const uniqueTypes = computed(() => {
  const tax = taxonomyState.data.value
  if (tax) {
    const domains = activeDomain.value ? tax.domains.filter(d => d.name === activeDomain.value) : tax.domains
    return [...new Set(domains.flatMap(d => d.types.map(t => t.name)))].sort()
  }
  return [...new Set((entityListState.data.value?.items ?? []).map(e => e.artifact_type))].sort()
})

// A re-ordered population has a different first page, so any change to the *server-resolved*
// order refetches from page one — including dropping it, so that paging afterwards is consistent
// with what is on screen. Switching between page-scoped columns needs no request at all.
const applySort = () => { if (orderKey() !== loadedOrder.value) load() }

const columns = computed<DataTableColumn[]>(() => [
  { key: 'name', label: 'Name', sortable: true },
  { key: 'artifact_type', label: 'Type', sortable: true },
  ...(activeDomain.value ? [] : [{ key: 'domain', label: 'Domain', sortable: true }]),
  {
    key: 'total',
    label: 'Connections',
    sortable: true,
    minWidth: '170px',
    note: isGroupView.value ? undefined : 'this page only',
    subColumns: [{ key: 'in', label: 'in' }, { key: 'sym', label: 'sym' }, { key: 'out', label: 'out' }],
  },
  { key: 'last_updated', label: 'Last modified', sortable: true },
  { key: 'status', label: 'Status', sortable: true },
])

const sortedEntities = computed(() => {
  // Group view: server returns all group items, client filters by domain + type.
  // Non-group view: server already filtered; client only re-ranks page-scoped columns.
  const items = isGroupView.value
    ? (entityListState.data.value?.items.filter(item =>
        (!typeFilter.value || item.artifact_type === typeFilter.value) &&
        (!activeDomain.value || item.domain === activeDomain.value)
      ) ?? [])
    : (entityListState.data.value?.items ?? [])
  return sortEntityRows(items, sortKey.value, sortDir.value === 'asc' ? 1 : -1)
})

const browseReturnQuery = computed(() => {
  const q: Record<string, string> = {}
  if (activeDomain.value) q.domain = activeDomain.value
  if (viewMode.value !== 'table') q.view = viewMode.value
  if (typeFilter.value) q.type = typeFilter.value
  return q
})

const pageTitle = computed(() => {
  const scope = isGlobal.value ? 'Enterprise ' : ''
  const domainPart = activeDomain.value ? `${getDomainLabel(activeDomain.value)} ` : ''
  return `${scope}${domainPart}Entities`
})
const displayCount = computed(() => {
  const total = entityListState.data.value?.total ?? 0
  if (isGroupView.value && (activeDomain.value || typeFilter.value)) return `${sortedEntities.value.length} / ${total}`
  return String(total)
})
</script>

<template>
  <ViewpointTablePage
    v-if="viewpointSlug"
    :slug="viewpointSlug"
  />
  <div
    v-else
    class="layout"
  >
    <aside
      v-if="!isGlobal"
      class="sidebar"
    >
      <div class="sidebar-header">
        <h2 class="sidebar-title">
          Project
        </h2>
        <RouterLink
          to="/entities/groups"
          class="manage-link"
          title="Manage projects"
        >
          ⚙
        </RouterLink>
      </div>

      <EntityGroupNavTree
        :groups="groupOptions"
        :active-group="activeGroup"
        :active-domain="activeDomain"
        :manageable="true"
        :show-archived="showArchivedGroups"
        :domain-counts="activeDomainCounts"
        :modules="modulesState.data.value ?? undefined"
        axis="model-project"
        @update:active-group="setGroup"
        @update:active-domain="setDomain"
        @update:show-archived="v => showArchivedGroups = v"
        @group-mutated="() => { load(); loadGroups(); loadTaxonomy() }"
        @navigate-to-groups="goToGroups"
      />
    </aside>

    <section class="content">
      <div class="content-header">
        <div>
          <h1 class="page-title">
            <span
              v-if="isGlobal"
              class="global-badge"
            >Enterprise</span>
            {{ pageTitle }}
            <span
              v-if="entityListState.data.value"
              class="count"
            >({{ displayCount }})</span>
          </h1>
          <p class="subtitle">
            <template v-if="isGlobal">
              Read-only view of the shared enterprise repository.
            </template>
            <template v-else>
              Filter by project and domain, then inspect the catalog as a sortable table or treemap.
            </template>
          </p>
        </div>
        <div class="actions">
          <TierFacet
            :model-value="tier"
            :allowed="LIST_TIERS"
            @update:model-value="selectTier"
          />
          <div class="view-toggle">
            <button
              class="toggle-btn"
              :class="{ 'toggle-btn--active': viewMode === 'table' }"
              @click="setViewMode('table')"
            >
              Table
            </button>
            <button
              class="toggle-btn"
              :class="{ 'toggle-btn--active': viewMode === 'treemap' }"
              @click="setViewMode('treemap')"
            >
              Treemap
            </button>
          </div>
          <RouterLink
            v-if="!isGlobal"
            to="/entity/create"
            class="create-btn"
          >
            + Create Entity
          </RouterLink>
          <RouterLink
            v-if="!isGlobal"
            to="/model/wizard"
            class="wizard-link"
            title="Guided modeling — questionnaires that walk you from motivation to application"
          >
            ✨ Guided
          </RouterLink>
        </div>
      </div>

      <div class="toolbar">
        <label class="toolbar-field">
          <span>Type</span>
          <select
            v-model="typeFilter"
            class="toolbar-select"
          >
            <option value="">All</option>
            <option
              v-for="type in uniqueTypes"
              :key="type"
              :value="type"
            >{{ type }}</option>
          </select>
        </label>
        <button
          v-if="!isGlobal"
          type="button"
          class="save-as-viewpoint-btn"
          title="Turn the current domain/type filters into a reusable viewpoint definition"
          @click="saveFiltersAsViewpoint"
        >
          💾 Save as viewpoint…
        </button>
      </div>

      <div
        v-if="entityListState.loading.value"
        class="state-msg"
      >
        Loading…
      </div>
      <div
        v-else-if="entityListState.errorMessage.value"
        class="state-msg state-msg--error"
      >
        {{ entityListState.errorMessage.value }}
      </div>

      <template v-else-if="entityListState.data.value">
        <div
          v-if="sortedEntities.length === 0"
          class="state-msg"
        >
          <template v-if="activeGroup">
            No entities in "{{ groupOptions.find(g => g.slug === activeGroup)?.name ?? activeGroup }}" yet.
          </template>
          <template v-else>
            No entities found{{ activeDomain ? ` in ${getDomainLabel(activeDomain)}` : '' }}{{ typeFilter ? ` of type "${typeFilter}"` : '' }}.
          </template>
        </div>

        <EntitiesTreemap
          v-else-if="viewMode === 'treemap'"
          :items="sortedEntities"
          :active-domain="activeDomain"
        />

        <template v-else>
          <div class="table-card">
            <DataTable
              v-model:sort-key="sortKey"
              v-model:sort-dir="sortDir"
              :columns="columns"
              :rows="sortedEntities"
              row-key="artifact_id"
              :row-class="entity => entity.is_global ? 'row--global' : undefined"
              @sort="applySort"
            >
              <template #name="{ row: entity }">
                <RouterLink :to="{ path: '/entity', query: { id: entity.artifact_id, ...browseReturnQuery } }">
                  {{ entity.name || friendlyEntityId(entity.artifact_id) }}
                </RouterLink>
                <TierBadge
                  v-if="entity.is_global && !isGlobal"
                  class="row-tier-badge"
                  :tier="tierFromIsGlobal(entity.is_global)"
                />
                <button
                  v-if="!activeGroup && groupOptions.length > 1 && entity.group && entity.group !== 'uncategorized'"
                  class="group-chip"
                  :title="`In group: ${entity.group}`"
                  @click="setGroup(entity.group ?? '')"
                >
                  {{ entity.group }}
                </button>
              </template>

              <template #artifact_type="{ row: entity }">
                <span class="type-cell">
                  <ArchimateTypeGlyph
                    :type="entity.artifact_type"
                    :size="15"
                    class="type-glyph"
                  />
                  <span class="mono">{{ entity.artifact_type }}</span>
                  <span
                    v-if="entity.specialization"
                    class="type-specialization"
                  >«{{ entity.specialization }}»</span>
                </span>
              </template>

              <template #domain="{ row: entity }">
                <span
                  class="domain-badge"
                  :class="`domain--${entity.domain}`"
                >{{ entity.domain }}</span>
              </template>

              <template #total="{ row: entity }">
                <span class="conn-counts">{{ getEntityConnectionTotal(entity) }}<span class="conn-split">({{ entity.conn_in ?? 0 }} / {{ entity.conn_sym ?? 0 }} / {{ entity.conn_out ?? 0 }})</span></span>
              </template>

              <template #last_updated="{ row: entity }">
                <span
                  class="stamp"
                  :title="lastModifiedTitle(entity.last_updated)"
                >{{ formatLastModified(entity.last_updated) }}</span>
              </template>

              <template #status="{ row: entity }">
                <span
                  class="status-badge"
                  :class="`status--${entity.status}`"
                >{{ entity.status }}</span>
              </template>
            </DataTable>
          </div>

          <div
            v-if="!isGroupView && pageCount > 1"
            class="pagination"
          >
            <button
              class="page-btn"
              :disabled="!hasPrev"
              @click="goToPrevPage"
            >
              ← Prev
            </button>
            <span class="page-info">Page {{ currentPage + 1 }} of {{ pageCount }}</span>
            <button
              class="page-btn"
              :disabled="!hasNext"
              @click="goToNextPage"
            >
              Next →
            </button>
          </div>
        </template>
      </template>
    </section>
  </div>
</template>

<style scoped>
.layout { display: flex; gap: 24px; }
.sidebar { width: 190px; flex-shrink: 0; }
.sidebar-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.sidebar-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; }
.manage-link { font-size: 14px; color: #9ca3af; text-decoration: none; line-height: 1; }
.manage-link:hover { color: #374151; }

.domain-list { list-style: none; display: flex; flex-direction: column; gap: 2px; }
.domain-btn { width: 100%; padding: 7px 10px; border: 0; border-left: 3px solid transparent; border-radius: 6px; background: transparent; color: #374151; cursor: pointer; font-size: 13px; text-align: left; }
.domain-btn:hover { background: #f3f4f6; }
.domain-btn.active { background: #eff6ff; color: #1d4ed8; font-weight: 500; }

.content { flex: 1; min-width: 0; }
.content-header, .actions, .view-toggle, .toolbar, .toolbar-field { display: flex; align-items: center; }
.content-header { justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.actions, .view-toggle { gap: 10px; }
.page-title { font-size: 22px; font-weight: 600; }
.subtitle, .count, .state-msg, .conn-split { color: #6b7280; }
.subtitle { margin-top: 2px; font-size: 13px; }
.count { margin-left: 6px; font-size: 14px; font-weight: 400; }
.toolbar { justify-content: space-between; margin-bottom: 14px; }
.toolbar-field { gap: 8px; }
.toolbar-field span { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; }
.toolbar-select, .toggle-btn { border: 1px solid #d1d5db; border-radius: 6px; background: white; color: #374151; }
.toolbar-select { min-width: 180px; padding: 7px 10px; }
.toggle-btn { padding: 7px 12px; cursor: pointer; font-size: 13px; }
.toggle-btn--active { background: #2563eb; border-color: #2563eb; color: white; }
.save-as-viewpoint-btn {
  appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280;
  border-radius: 7px; padding: 7px 12px; font-size: 12.5px; font-weight: 600; cursor: pointer;
}
.save-as-viewpoint-btn:hover { border-color: #6366f1; color: #4338ca; }
.create-btn { padding: 8px 14px; border-radius: 6px; background: #16a34a; color: white; font-size: 13px; font-weight: 500; white-space: nowrap; }
.create-btn:hover { background: #15803d; text-decoration: none; }
.wizard-link {
  padding: 8px 12px; border-radius: 6px; border: 1px solid #bfdbfe; color: #1d4ed8;
  font-size: 13px; white-space: nowrap; background: #fff;
}
.wizard-link:hover { background: #eff6ff; text-decoration: none; }

.table-card { background: white; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }
.stamp { font-size: 12px; color: #6b7280; white-space: nowrap; }
.type-cell { display: inline-flex; align-items: center; gap: 8px; }
.type-glyph { color: #374151; fill: none; flex: 0 0 auto; }
.type-specialization { font-size: 11px; font-style: italic; color: #6d28d9; }
.mono, .conn-counts { font-family: monospace; }
.mono { font-size: 12px; color: #374151; }
.conn-counts { font-size: 12px; white-space: nowrap; }
.state-msg--error { color: #dc2626; }
.global-badge { display: inline-block; background: #fef3c7; color: #92400e; border: 1px solid #fde68a; border-radius: 4px; padding: 1px 7px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin-right: 8px; vertical-align: middle; }
.row-tier-badge { margin-left: 8px; vertical-align: middle; }
.group-chip { display: inline-block; margin-left: 6px; background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; border-radius: 3px; padding: 0 5px; font-size: 10px; font-weight: 500; vertical-align: middle; cursor: pointer; }
.group-chip:hover { background: #bae6fd; }
.table-card :deep(.row--global) td { background: #fffbeb; }
.table-card :deep(.row--global):hover td { background: #fef9e7; }

.pagination { display: flex; align-items: center; gap: 12px; padding: 12px 0; justify-content: center; }
.page-btn { padding: 6px 14px; border: 1px solid #d1d5db; border-radius: 6px; background: white; color: #374151; cursor: pointer; font-size: 13px; }
.page-btn:hover:not(:disabled) { background: #f3f4f6; }
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.page-info { font-size: 13px; color: #6b7280; }
</style>
