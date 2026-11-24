<script setup lang="ts">
/**
 * The assurance node list: filters, the Table/Treemap switch, and whichever of the two is showing.
 *
 * Split out of `AssuranceBrowseView`, which had grown past the source-length policy while gaining
 * the columns and the switch. The view keeps what only it can do — loading, routing, authoring —
 * and this owns presenting a list of nodes.
 *
 * The two modes and the toggle itself are the architecture catalog's, down to the markup and the
 * CSS: an analyst moving between the two areas should not have to learn a second set of controls
 * that look almost the same. It briefly offered a bespoke "Tree" of grouped rows in the Treemap
 * button's place, which is worse than either — grouping by node type is what the filing tree in the
 * nav does, and what a treemap adds is relative weight, which no list gives you.
 */
import { RouterLink } from 'vue-router'
import DataTable from './DataTable.vue'
import FilterBar from './FilterBar.vue'
import AssuranceTreemap from './AssuranceTreemap.vue'
import { tlpColor } from './tlp'
import { assuranceNodeDetailRoute } from '../router/artifactRoutes'
import { directionSplit } from './connectionCounts'
import type { DataTableColumn, SortDirection, SortRequest } from './DataTable.types'
import type { FilterSpec } from './FilterBar.vue'
import { formatLastModified, lastModifiedTitle } from '../lib/lastModified'
import {
  nodeConnectionTotal, nodeConnections,
  type AssuranceBrowseNode as AssuranceNode,
} from '../views/AssuranceBrowseView.helpers'

defineProps<{
  rows: readonly AssuranceNode[]
  columns: readonly DataTableColumn[]
  filters: readonly FilterSpec[]
  optionsFor: ReadonlyMap<string, readonly string[]>
  selection: Record<string, string>
  sortKey: string | null
  sortDir: SortDirection
  viewMode: 'table' | 'treemap'
  loading: boolean
  emptyMessage: string
  selectedNodeId: string | null
}>()

const emit = defineEmits<{
  'update:selection': [value: Record<string, string>]
  'update:sortKey': [value: string | null]
  'update:sortDir': [value: SortDirection]
  'set-view-mode': [mode: 'table' | 'treemap']
  sort: [request: SortRequest]
  select: [nodeId: string]
}>()
</script>

<template>
  <div class="browse-list-panel">
    <FilterBar
      :model-value="selection"
      :filters="filters"
      :options-for="optionsFor"
      @update:model-value="emit('update:selection', $event)"
    />

    <div class="list-toolbar">
      <div class="view-toggle">
        <button
          type="button"
          class="toggle-btn"
          :class="{ 'toggle-btn--active': viewMode === 'table' }"
          @click="emit('set-view-mode', 'table')"
        >
          Table
        </button>
        <button
          type="button"
          class="toggle-btn"
          :class="{ 'toggle-btn--active': viewMode === 'treemap' }"
          @click="emit('set-view-mode', 'treemap')"
        >
          Treemap
        </button>
      </div>
    </div>
    <div class="list-count">
      {{ rows.length }} node{{ rows.length === 1 ? '' : 's' }}
    </div>

    <div
      v-if="loading"
      class="list-loading"
    >
      Loading nodes…
    </div>
    <p
      v-else-if="viewMode === 'treemap' && rows.length === 0"
      class="list-loading"
    >
      {{ emptyMessage }}
    </p>
    <AssuranceTreemap
      v-else-if="viewMode === 'treemap'"
      :items="rows"
    />
    <div
      v-else
      class="node-table-scroll"
    >
      <DataTable
        :sort-key="sortKey"
        :sort-dir="sortDir"
        :columns="columns"
        :rows="rows"
        row-key="node_id"
        selectable
        :selected-key="selectedNodeId"
        :empty-message="emptyMessage"
        @update:sort-key="emit('update:sortKey', $event)"
        @update:sort-dir="emit('update:sortDir', $event)"
        @sort="emit('sort', $event)"
        @row-click="emit('select', $event)"
      >
        <template #node_type="{ row: node }">
          <span class="node-type-badge">{{ node.node_type }}</span>
        </template>
        <template #name="{ row: node }">
          <RouterLink
            class="node-name node-name--link"
            :to="assuranceNodeDetailRoute(node.node_id)"
            @click.stop
          >
            {{ node.name }}
          </RouterLink>
        </template>
        <template #status="{ row: node }">
          <span
            v-if="node.status"
            class="node-status"
          >{{ node.status }}</span>
        </template>
        <template #concern_class="{ row: node }">
          <span
            v-if="node.concern_class"
            class="node-concern"
          >{{ node.concern_class }}</span>
        </template>
        <template #total="{ row: node }">
          {{ nodeConnectionTotal(node as AssuranceNode) }}<span
            class="conn-split"
          >({{ directionSplit(nodeConnections(node as AssuranceNode)) }})</span>
        </template>
        <template #tlp="{ row: node }">
          <span
            v-if="node.tlp && node.tlp !== 'TLP:WHITE'"
            class="node-tlp"
            :style="{ color: tlpColor(String(node.tlp)) }"
          >{{ node.tlp }}</span>
        </template>
        <template #binding_status="{ row: node }">
          <span
            v-if="node.binding_status"
            class="node-binding"
            :class="`node-binding--${node.binding_status}`"
          >{{ node.binding_status }}</span>
        </template>
        <template #updated_at="{ row: node }">
          <span
            class="stamp"
            :title="lastModifiedTitle(String(node.updated_at ?? ''))"
          >{{ formatLastModified(String(node.updated_at ?? '')) }}</span>
        </template>
      </DataTable>
    </div>
  </div>
</template>

<style scoped>
.browse-list-panel {
  flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden;
}
.list-toolbar { display: flex; align-items: center; gap: 10px; padding: 8px 16px 0; }
.view-toggle { display: inline-flex; align-items: center; gap: 10px; }
/* Deliberately the architecture catalog's own numbers (EntitiesView), not an approximation of
   them: two toggles that differ by two pixels of padding read as two different controls. */
.toggle-btn {
  font-size: 13px; padding: 7px 12px; border: 1px solid var(--border-strong); border-radius: 6px;
  background: var(--surface); cursor: pointer; color: var(--text-2);
}
.toggle-btn:hover:not(.toggle-btn--active) { background: var(--soft); }
/* Selected keeps its own colours through hover, as elsewhere: a bare :hover rule would
   otherwise restore the pale background while the white label stayed. */
.toggle-btn--active { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
.toggle-btn--active:hover { background: var(--accent-strong); }

.list-count { font-size: 11.5px; color: var(--muted); padding: 6px 16px; }
.list-loading { font-size: 13px; color: var(--muted); padding: 16px; }
.node-table-scroll { flex: 1; overflow: auto; }

.node-type-badge {
  font-size: 11px; background: var(--indigo-soft); color: var(--indigo-text); border-radius: 4px; padding: 1px 6px;
}
.node-name--link { color: var(--accent-strong); text-decoration: none; }
.node-name--link:hover { text-decoration: underline; }
.node-status, .node-concern { font-size: 11.5px; color: var(--text-2); }
/* The direction breakdown reads as a gloss on the total, not a second number. */
.conn-split { margin-left: 6px; font-size: 11px; color: var(--muted); }
.node-tlp { font-size: 11px; font-weight: 600; }
.node-binding { font-size: 11px; color: var(--text-2); }
.stamp { font-size: 11.5px; color: var(--muted); }
</style>
