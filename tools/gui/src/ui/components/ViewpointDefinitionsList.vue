<script setup lang="ts">
import { diagramDetailRoute } from '../router/artifactRoutes'
/**
 * List mode of the viewpoints management view: browse the effective merged catalog as a
 * decision surface (description, representation, needs-input marker, search/sort/tier
 * filter) and route each definition to its representation-appropriate execution surface.
 * Injects the model service itself for pins/delete, and emits only what the parent must
 * react to: switching into create/edit mode, and a delete having changed the catalog.
 */
import { computed, inject, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { tierFromViewpointFilter, viewpointFilterFromTier } from '../composables/listRequestParams'
import { tierDisplayLowercase } from './TierBadge.helpers'
import { useTierFacet } from '../composables/useTierFacet'
import { useWriteBlock } from '../composables/useWriteBlock'
import { VIEWPOINT_TIERS } from '../lib/tierUrlState'
import { readApiErrorBody, readErrorMessage } from '../lib/errors'
import { viewpointReferencedDetails } from '../../domain/schemas/errors'
import type { ViewpointDefinitionEnvelope, ViewpointReferencer } from '../../domain'
import { executionRouteFor } from '../views/ViewpointsManagementView.helpers'
import {
  CREATE_CAPABILITY_COPY, filterAndSortDefinitions, type CatalogSortDirection, type CatalogSortKey,
  nextCatalogSort,
  toggledMember,
} from './ViewpointDefinitionsList.helpers'
import ViewpointCatalogRow from './ViewpointCatalogRow.vue'

const props = defineProps<{ definitions: readonly ViewpointDefinitionEnvelope[] }>()
const emit = defineEmits<{
  create: []; edit: [envelope: ViewpointDefinitionEnvelope]; refresh: []; error: [message: string]
}>()

const svc = inject(modelServiceKey)!
const writeBlocked = useWriteBlock()
const router = useRouter()

const executeViewpoint = (envelope: ViewpointDefinitionEnvelope) => void router.push(executionRouteFor(envelope))

// ── Search / tier filter (URL-backed) / sort ─────────────────────────────────
const search = ref('')
const { tier, setTier } = useTierFacet(VIEWPOINT_TIERS)
const tierFilter = computed<ViewpointDefinitionEnvelope['tier'] | ''>({
  get: () => viewpointFilterFromTier(tier.value),
  set: (value) => setTier(tierFromViewpointFilter(value)),
})
const sortKey = ref<CatalogSortKey | null>(null)
const sortDirection = ref<CatalogSortDirection>('asc')
const toggleSort = (key: CatalogSortKey) => {
  const next = nextCatalogSort(sortKey.value, sortDirection.value, key)
  sortKey.value = next.key
  sortDirection.value = next.direction
}
const visibleDefinitions = computed(() =>
  filterAndSortDefinitions(props.definitions, search.value, tierFilter.value, sortKey.value, sortDirection.value))
const ariaSortFor = (key: CatalogSortKey) =>
  sortKey.value === key ? (sortDirection.value === 'asc' ? 'ascending' : 'descending') : undefined

const expandedScopes = ref<Set<string>>(new Set())
const toggleScope = (slug: string) => { expandedScopes.value = toggledMember(expandedScopes.value, slug) }

// ── Pins (Home quick access) ─────────────────────────────────────────────────
const pinnedSlugs = ref<Set<string>>(new Set())
onMounted(() => {
  void Effect.runPromise(svc.getViewpointPins()).then((pins) => { pinnedSlugs.value = new Set(pins.slugs) })
})
const isPinned = (slug: string) => pinnedSlugs.value.has(slug)
const togglePin = (slug: string) => {
  const next = new Set(pinnedSlugs.value)
  if (next.has(slug)) next.delete(slug)
  else next.add(slug)
  void Effect.runPromise(svc.setViewpointPins([...next])).then((pins) => { pinnedSlugs.value = new Set(pins.slugs) })
}

/** Delete-blocked-while-referenced state: kept local (not just bubbled up as a flat error
 * string) so the referencers can be rendered as actionable links to the diagram/matrix
 * pinning this definition, not just named in prose. */
const blockedDelete = ref<{ slug: string; referencers: readonly ViewpointReferencer[] } | null>(null)

const openReferencer = (referencer: ViewpointReferencer) => {
  void router.push(diagramDetailRoute(referencer.artifact_id))
}

const deleteDefinition = (envelope: ViewpointDefinitionEnvelope) => {
  if (!window.confirm(`Delete viewpoint '${envelope.slug}'?`)) return
  blockedDelete.value = null
  // A deletion reports nothing, so success is the absence of a failure. A refusal arrives as a
  // typed error: `viewpoint_referenced` carries the views that still pin the slug, which is what
  // makes them renderable as links instead of named in a sentence.
  Effect.runPromise(svc.deleteViewpointDefinition(envelope.slug)).then(() => {
    emit('refresh')
  }).catch((reason: unknown) => {
    const body = readApiErrorBody(reason)
    const referenced = body === null ? null : viewpointReferencedDetails(body)
    if (referenced !== null) {
      blockedDelete.value = { slug: envelope.slug, referencers: referenced.referencers }
      return
    }
    emit('error', body?.message ?? readErrorMessage(reason))
  })
}
</script>

<template>
  <div>
    <div class="catalog-toolbar">
      <div class="create-block">
        <button
          type="button"
          class="primary-btn"
          :disabled="writeBlocked"
          :title="writeBlocked
            ? 'Creating a viewpoint needs engagement write access — this session is read-only'
            : 'Starts a NEW blank definition (no lineage). To adapt an existing one, open it and use Save as…'"
          @click="emit('create')"
        >
          + Create viewpoint
        </button>
        <RouterLink
          to="/viewpoints/query"
          class="query-model-btn"
          title="Compose and run a query with any presentation without saving anything — Save as… later to keep it"
        >
          ⌕ Query model
        </RouterLink>
        <span class="capability-copy">{{ CREATE_CAPABILITY_COPY }}</span>
      </div>
      <div class="filter-block">
        <input
          v-model="search"
          type="search"
          class="catalog-search"
          placeholder="Search name, slug, description…"
          aria-label="Search viewpoints"
        >
        <select
          v-model="tierFilter"
          class="tier-filter"
          aria-label="Filter by tier"
        >
          <option value="">
            all tiers
          </option>
          <option
            v-for="tierOption in VIEWPOINT_TIERS"
            :key="tierOption"
            :value="tierOption"
          >
            {{ tierDisplayLowercase(tierOption) }}
          </option>
        </select>
      </div>
    </div>
    <div
      v-if="blockedDelete"
      class="blocked-panel"
    >
      <p>
        Can't delete '{{ blockedDelete.slug }}' — still referenced by:
      </p>
      <ul>
        <li
          v-for="referencer in blockedDelete.referencers"
          :key="referencer.artifact_id"
        >
          <button
            type="button"
            class="referencer-link"
            @click="openReferencer(referencer)"
          >
            {{ referencer.artifact_id }} ({{ referencer.target_kind }})
          </button>
        </li>
      </ul>
      <button
        type="button"
        class="btn"
        @click="blockedDelete = null"
      >
        Dismiss
      </button>
    </div>
    <p
      v-if="visibleDefinitions.length === 0"
      class="empty-state"
    >
      <template v-if="definitions.length === 0">
        No viewpoints yet.
      </template>
      <template v-else>
        No viewpoint matches this search.
      </template>
      No viewpoint fits? <button
        type="button"
        class="empty-create-link"
        :disabled="writeBlocked"
        @click="emit('create')"
      >
        Create one
      </button> — {{ CREATE_CAPABILITY_COPY.toLowerCase() }}
    </p>
    <table
      v-else
      class="def-table"
    >
      <thead>
        <tr>
          <th
            class="sortable"
            :aria-sort="ariaSortFor('name')"
            @click="toggleSort('name')"
          >
            Viewpoint <span
              v-if="sortKey === 'name'"
              class="sort-arrow"
            >{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
          </th>
          <th
            class="sortable"
            :aria-sort="ariaSortFor('version')"
            @click="toggleSort('version')"
          >
            Version <span
              v-if="sortKey === 'version'"
              class="sort-arrow"
            >{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
          </th>
          <th
            class="sortable"
            :aria-sort="ariaSortFor('tier')"
            @click="toggleSort('tier')"
          >
            Tier <span
              v-if="sortKey === 'tier'"
              class="sort-arrow"
            >{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
          </th>
          <th>Scope</th><th />
        </tr>
      </thead>
      <tbody>
        <ViewpointCatalogRow
          v-for="def in visibleDefinitions"
          :key="def.slug"
          :def="def"
          :pinned="isPinned(def.slug)"
          :scope-expanded="expandedScopes.has(def.slug)"
          :write-blocked="writeBlocked"
          @execute="executeViewpoint(def)"
          @edit="emit('edit', def)"
          @delete="deleteDefinition(def)"
          @toggle-pin="togglePin(def.slug)"
          @toggle-scope="toggleScope(def.slug)"
        />
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.catalog-toolbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 12px; flex-wrap: wrap; }
.create-block { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.capability-copy { font-size: 12px; color: #6b7280; }
.filter-block { display: flex; align-items: center; gap: 8px; }
.catalog-search { padding: 7px 10px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 13px; min-width: 220px; }
.tier-filter { padding: 7px 8px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 12.5px; background: #fff; color: #374151; }
.primary-btn { background: #6366f1; color: #fff; border: none; border-radius: 7px; padding: 8px 16px; font-weight: 600; cursor: pointer; }
.primary-btn:disabled { opacity: .5; cursor: not-allowed; }
.empty-state { font-size: 13px; color: #6b7280; background: #f9fafb; border: 1px dashed #d1d5db; border-radius: 8px; padding: 14px 16px; }
.query-model-btn { display: inline-flex; align-items: center; text-decoration: none; color: #4338ca; border: 1px solid #c7d2fe; border-radius: 7px; padding: 7px 14px; font-weight: 600; font-size: 13px; background: #fff; }
.query-model-btn:hover { background: #eef2ff; }
.empty-create-link { appearance: none; border: none; background: none; color: #4338ca; font-weight: 600; text-decoration: underline; cursor: pointer; font-size: 13px; padding: 0; }
.empty-create-link:disabled { color: #9ca3af; cursor: not-allowed; }
.blocked-panel { background: #fee2e2; color: #991b1b; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 13px; }
.blocked-panel ul { margin: 6px 0; padding-left: 18px; }
.referencer-link { appearance: none; border: none; background: none; color: #991b1b; text-decoration: underline; cursor: pointer; font-size: 13px; padding: 0; }
.def-table { width: 100%; border-collapse: collapse; }
.def-table th, .def-table td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #e5e7eb; font-size: 13px; vertical-align: top; }
.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
.sortable:hover { color: #4338ca; }
.sort-arrow { font-size: 9px; }
.btn { appearance: none; border: 1px solid #d1d5db; background: #fff; color: #374151; border-radius: 6px; padding: 5px 12px; font-size: 12.5px; font-weight: 600; cursor: pointer; }
.btn:hover:not(:disabled) { border-color: #6366f1; color: #4338ca; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn--danger:hover:not(:disabled) { border-color: #dc2626; color: #b91c1c; background: #fef2f2; }
</style>
