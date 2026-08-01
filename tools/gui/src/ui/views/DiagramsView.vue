<script setup lang="ts">
import { diagramCreateRoute, diagramDetailRoute, matrixCreateRoute } from '../router/artifactRoutes'
import { computed, inject, ref } from 'vue'
import { RouterLink } from 'vue-router'
import type { DiagramTypeSummary } from '../../domain'
import { modelServiceKey } from '../keys'
import { LIST_TIERS } from '../lib/tierUrlState'
import { tierFromIsGlobal } from '../components/TierBadge.helpers'
import { useDiagramsListState } from '../composables/useDiagramsListState'
import DownloadMenu from '../components/DownloadMenu.vue'
import GroupSelector from '../components/GroupSelector.vue'
import TierBadge from '../components/TierBadge.vue'
import TierFacet from '../components/TierFacet.vue'

const svc = inject(modelServiceKey)!

const {
  tier, selectTier, collectionsAvailable,
  diagramsState, diagramKinds, showArchivedGroups,
  selectedType, activeGroup, setGroup, goToGroups,
  groupOptions, filteredItems, selectType, load, loadGroups,
} = useDiagramsListState(svc)

const diagramFilters = computed(() => {
  const seen = new Set<string>(['', 'archimate-all'])
  const filters = [
    { key: '', label: 'All' },
    { key: 'archimate-all', label: 'ArchiMate' },
  ]
  for (const kind of diagramKinds.value) {
    if (seen.has(kind.key)) continue
    seen.add(kind.key)
    filters.push({ key: kind.key, label: kind.label.replace(/\s+Diagram$/i, '') })
  }
  filters.push({ key: 'other', label: 'Other' })
  return filters
})
const createDiagramRoute = (kind: DiagramTypeSummary) => {
  if (kind.key === 'matrix') return matrixCreateRoute()
  return { path: diagramCreateRoute(), query: { type: kind.key } }
}
const showCreateMenu = ref(false)
let _closeMenuTimer: ReturnType<typeof setTimeout> | null = null
const closeCreateMenu = () => { _closeMenuTimer = setTimeout(() => { showCreateMenu.value = false }, 150) }
const keepCreateMenu = () => { if (_closeMenuTimer !== null) { clearTimeout(_closeMenuTimer); _closeMenuTimer = null } }

const diagramTypeLabel = (diagramType: string): string => {
  if (diagramType === 'matrix') return 'matrix'
  if (diagramType === 'archimate') return 'archimate'
  if (diagramType.startsWith('archimate-')) return diagramType.replace('archimate-', '')
  return diagramType
}
</script>

<template>
  <div class="layout">
    <aside
      v-if="collectionsAvailable"
      class="sidebar"
    >
      <div class="sidebar-header">
        <h2 class="sidebar-title">
          Collection
        </h2>
        <RouterLink
          to="/diagrams/groups"
          class="manage-link"
          title="Manage collections"
        >
          ⚙
        </RouterLink>
      </div>
      <GroupSelector
        :groups="groupOptions"
        :model-value="activeGroup"
        :show-archived="showArchivedGroups"
        :manageable="true"
        axis="diagram-collection"
        @update:model-value="setGroup"
        @update:show-archived="v => showArchivedGroups = v"
        @group-mutated="() => { load(); loadGroups() }"
        @navigate-to-groups="goToGroups"
      />
    </aside>
    <section class="content">
      <div class="page-header">
        <h1 class="page-title">
          Diagrams
        </h1>
        <div
          class="create-wrap"
          @mouseenter="keepCreateMenu"
        >
          <button
            class="create-btn"
            @click="showCreateMenu = !showCreateMenu"
            @blur="closeCreateMenu"
          >
            + Create Diagram ▾
          </button>
          <div
            v-if="showCreateMenu"
            class="create-menu"
            @mouseenter="keepCreateMenu"
          >
            <RouterLink
              v-for="kind in diagramKinds"
              :key="kind.key"
              :to="createDiagramRoute(kind)"
              class="create-opt"
              @click="showCreateMenu = false"
            >
              {{ kind.label }}
            </RouterLink>
          </div>
        </div>
      </div>

      <div class="facet-bar">
        <TierFacet
          :model-value="tier"
          :allowed="LIST_TIERS"
          @update:model-value="selectTier"
        />
      </div>

      <div class="filter-bar">
        <button
          v-for="dt in diagramFilters"
          :key="dt.key"
          class="filter-btn"
          :class="{ 'filter-btn--active': selectedType === dt.key }"
          @click="selectType(dt.key)"
        >
          {{ dt.label }}
        </button>
      </div>

      <div
        v-if="diagramsState.loading.value"
        class="state-msg"
      >
        Loading...
      </div>
      <div
        v-else-if="diagramsState.errorMessage.value"
        class="state-msg state-msg--error"
      >
        {{ diagramsState.errorMessage.value }}
      </div>

      <template v-else-if="diagramsState.data.value">
        <p
          v-if="filteredItems.length === 0 && activeGroup"
          class="state-msg"
        >
          No diagrams in "{{ groupOptions.find(g => g.slug === activeGroup)?.name ?? activeGroup }}" yet.
        </p>
        <p class="result-count">
          {{ filteredItems.length }} diagram{{ filteredItems.length !== 1 ? 's' : '' }}
        </p>

        <div class="diagram-grid">
          <div
            v-for="d in filteredItems"
            :key="d.artifact_id"
            class="diagram-card card"
          >
            <RouterLink
              :to="diagramDetailRoute(d.artifact_id)"
              class="card-link"
            >
              <div class="diagram-name">
                {{ d.name }}
              </div>
              <div class="diagram-meta">
                <span class="diagram-type-badge">{{ diagramTypeLabel(d.diagram_type) }}</span>
                <TierBadge :tier="tierFromIsGlobal(d.is_global)" />
                <span
                  class="status-badge"
                  :class="`status--${d.status}`"
                >{{ d.status }}</span>
              </div>
              <div class="diagram-id mono">
                {{ d.artifact_id }}
              </div>
            </RouterLink>
            <DownloadMenu
              :diagram-id="d.artifact_id"
              :diagram-name="d.name"
              class="card-dl"
            />
          </div>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.layout { display: flex; gap: 24px; }
.sidebar { width: 190px; flex-shrink: 0; }
.sidebar-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.sidebar-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; }
.manage-link { font-size: 14px; color: #9ca3af; text-decoration: none; }
.manage-link:hover { color: #374151; }
.content { flex: 1; min-width: 0; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.page-title { font-size: 22px; font-weight: 600; margin-bottom: 0; display: flex; align-items: center; gap: 8px; }
.create-wrap { position: relative; }
.create-btn {
  padding: 7px 14px; background: #2563eb; color: white; border-radius: 6px;
  font-size: 13px; font-weight: 500; border: none; cursor: pointer;
}
.create-btn:hover { background: #1d4ed8; }
.create-menu {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 20;
  background: white; border: 1px solid #e5e7eb; border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,.12); min-width: 170px; padding: 4px 0;
}
.create-opt {
  display: block; padding: 8px 14px; font-size: 13px; color: #374151;
  text-decoration: none; white-space: nowrap;
}
.create-opt:hover { background: #f9fafb; color: #1d4ed8; text-decoration: none; }
.facet-bar { margin-bottom: 12px; }
.result-count { font-size: 13px; color: #6b7280; margin-bottom: 12px; }
.state-msg { color: #6b7280; }
.state-msg--error { color: #dc2626; }
.mono { font-family: monospace; }

.filter-bar { display: flex; gap: 6px; margin-bottom: 20px; flex-wrap: wrap; }
.filter-btn {
  padding: 5px 12px; border-radius: 6px; border: 1px solid #d1d5db;
  background: white; font-size: 13px; cursor: pointer; color: #374151;
}
/* Hover is excluded on the selected filter and given its own darker shade there. A bare
   `:hover` rule outranks the single-class active rule, so hovering the selected filter
   restored the pale hover background under its white label. */
.filter-btn:hover:not(.filter-btn--active) { background: #f9fafb; }
.filter-btn--active { background: #2563eb; color: white; border-color: #2563eb; }
.filter-btn--active:hover { background: #1d4ed8; }

.diagram-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px;
}
.card {
  background: white; border-radius: 8px; border: 1px solid #e5e7eb;
  position: relative;
}
.card:hover { box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.card-link { display: block; padding: 16px; color: inherit; text-decoration: none; }
.card-link:hover { text-decoration: none; }
.card-dl { position: absolute; top: 10px; right: 10px; }

.diagram-name { font-weight: 600; font-size: 14px; margin-bottom: 8px; }
.diagram-meta { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; flex-wrap: wrap; }
.diagram-id { font-size: 11px; color: #9ca3af; }

.diagram-type-badge {
  padding: 2px 8px; border-radius: 4px; font-size: 11px;
  background: #dbeafe; color: #1e40af; font-weight: 500;
}
.status-badge { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.status--draft { background: #f3f4f6; color: #6b7280; }
.status--active { background: #dcfce7; color: #166534; }
.status--deprecated { background: #fee2e2; color: #991b1b; }
</style>
