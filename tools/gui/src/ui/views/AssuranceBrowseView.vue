<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AssuranceNodeDetail from '../components/AssuranceNodeDetail.vue'
import AssuranceNodeForm from './AssuranceNodeForm.vue'
import type { AssuranceNodeFormData } from './AssuranceNodeForm.vue'
import AssuranceEdgePicker from '../components/AssuranceEdgePicker.vue'
import AssuranceAnalysisPicker from '../components/AssuranceAnalysisPicker.vue'
import { nodesUrlForAnalysis } from '../components/AssuranceAnalysisPicker.helpers'
import WithheldNotice from '../components/WithheldNotice.vue'
import AssuranceNodeList from '../components/AssuranceNodeList.vue'
import AssuranceStoreStatus from '../components/AssuranceStoreStatus.vue'
import AssuranceWizardNav from '../components/AssuranceWizardNav.vue'
import type { SortDirection, SortRequest } from '../components/DataTable.types'
import {
  BROWSE_COLUMNS,
  DEFAULT_SORT_DIRECTION,
  DEFAULT_SORT_FIELD,
  NODE_FILTERS,
  filterNodes,
  filterOptions,
  noFilters,
  analysisScopeOf,
  scopeNodes,
  storeAnalysisId,
  type AssuranceBrowseNode as AssuranceNode,
} from './AssuranceBrowseView.helpers'

interface NodesResponse {
  nodes: AssuranceNode[]
  count: number
  visibility_limited?: boolean
}

const route = useRoute()
const router = useRouter()

const nodes = ref<AssuranceNode[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const visibilityLimited = ref(false)

// Analysis scope lives in the URL — see `analysisScopeOf` in the helpers for why.
const analysisScope = computed(() => analysisScopeOf(route.query['analysis']))
const analysisId = computed(() => storeAnalysisId(analysisScope.value))

const replaceQuery = (patch: Record<string, string | undefined>) =>
  void router.replace({ query: { ...route.query, ...patch }, hash: route.hash })

const setAnalysis = (value: string | null) => replaceQuery({ analysis: value || undefined })

// Filters, one per narrowable field (see NODE_FILTERS).
const filters = ref(noFilters())

// The architecture catalog's own two modes and query; see `AssuranceNodeList` for the reasoning.
const viewMode = computed<'table' | 'treemap'>(() =>
  route.query['view'] === 'treemap' ? 'treemap' : 'table')

const setViewMode = (mode: 'table' | 'treemap') =>
  replaceQuery({ view: mode === 'table' ? undefined : mode })

// The store resolves the order before the exposure filter, so ordering is a request parameter.
const sortKey = ref<string | null>(DEFAULT_SORT_FIELD)
const sortDir = ref<SortDirection>(DEFAULT_SORT_DIRECTION)

// Selected node for detail / edit panels
const selectedNodeId = ref<string | null>(null)
const selectedNode = computed(() => nodes.value.find(n => n.node_id === selectedNodeId.value) ?? null)

// Panel mode: 'detail' | 'create' | 'edit' | 'add-edge'
const panelMode = ref<'detail' | 'create' | 'edit' | 'add-edge'>('detail')
const formLoading = ref(false)
const formError = ref<string | null>(null)

// Derived: unique filter options from loaded nodes
const optionsFor = computed(() => new Map(
  NODE_FILTERS.map(({ field }) => [field, filterOptions(nodes.value, field)]),
))

const filtered = computed(() =>
  filterNodes(scopeNodes(nodes.value, analysisScope.value), filters.value))

// An empty list means two different things, and the reader needs to know which.
const emptyMessage = computed(() => nodes.value.length === 0
  ? 'No assurance nodes in the store.'
  : 'No nodes match the current filters.')

// A third header click clears the sort; the listing has no meaningful unordered state, so it
// returns to the default order rather than leaving the reader with an arbitrary one.
function applySort(next: SortRequest) {
  if (next.key === null) {
    sortKey.value = DEFAULT_SORT_FIELD
    sortDir.value = DEFAULT_SORT_DIRECTION
  }
  void loadNodes()
}

async function loadNodes() {
  loading.value = true
  error.value = null
  try {
    const resp = await fetch(nodesUrlForAnalysis(analysisId.value, sortKey.value ?? undefined, sortDir.value))
    if (resp.status === 423) {
      error.value = 'The assurance store is locked. Run `arch-assurance unlock` and restart the backend.'
      return
    }
    if (!resp.ok) {
      error.value = `Failed to load nodes (HTTP ${resp.status})`
      return
    }
    const body = await resp.json() as NodesResponse
    nodes.value = body.nodes
    visibilityLimited.value = body.visibility_limited ?? false
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

/**
 * Open a node.
 *
 * A page, not a side panel. The panel squeezed the list into 400px to show a node beside it,
 * so reading one node cost most of the surface you were reading it from — and the standalone
 * page already existed, reachable only from a link inside the panel. The architecture side has
 * always worked this way: the table stays whole and `/entity` is its own page.
 */
function selectNode(nodeId: string) {
  void router.push({ path: `/assurance/node/${nodeId}` })
}

function closePanel() {
  selectedNodeId.value = null
  panelMode.value = 'detail'
  formError.value = null
}

function openCreate() {
  selectedNodeId.value = null
  panelMode.value = 'create'
  formError.value = null
}

function openEdit() {
  if (!selectedNodeId.value) return
  panelMode.value = 'edit'
  formError.value = null
}

function openAddEdge() {
  if (!selectedNodeId.value) return
  panelMode.value = 'add-edge'
  formError.value = null
}

function backToDetail() {
  panelMode.value = 'detail'
  formError.value = null
}

async function handleCreate(data: AssuranceNodeFormData) {
  // A node records which analysis produced it, so an unscoped browse has nowhere to put one.
  if (!analysisId.value) { formError.value = 'Choose an analysis first.'; return }
  formLoading.value = true
  formError.value = null
  try {
    const url = `/api/assurance/analyses/${encodeURIComponent(analysisId.value)}/nodes`
    const init = { method: 'POST', headers: { 'Content-Type': 'application/json' } }
    const resp = await fetch(url, { ...init, body: JSON.stringify(data) })
    if (resp.status === 423) { formError.value = 'Store is locked.'; return }
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({})) as Record<string, unknown>
      formError.value = typeof body['error'] === 'string' ? body['error'] : `HTTP ${resp.status}`
      return
    }
    await loadNodes()
    panelMode.value = 'detail'
  } catch (e) {
    formError.value = String(e)
  } finally {
    formLoading.value = false
  }
}

async function handleEdit(data: AssuranceNodeFormData) {
  if (!selectedNodeId.value) return
  formLoading.value = true
  formError.value = null
  try {
    const resp = await fetch(`/api/assurance/nodes/${selectedNodeId.value}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (resp.status === 423) { formError.value = 'Store is locked.'; return }
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({})) as Record<string, unknown>
      formError.value = typeof body['error'] === 'string' ? body['error'] : `HTTP ${resp.status}`
      return
    }
    await loadNodes()
    panelMode.value = 'detail'
  } catch (e) {
    formError.value = String(e)
  } finally {
    formLoading.value = false
  }
}

async function handleDelete() {
  if (!selectedNodeId.value) return
  if (!confirm('Delete this node and all its edges? This cannot be undone.')) return
  formLoading.value = true
  formError.value = null
  try {
    const resp = await fetch(`/api/assurance/nodes/${selectedNodeId.value}`, { method: 'DELETE' })
    if (resp.status === 423) { formError.value = 'Store is locked.'; return }
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({})) as Record<string, unknown>
      formError.value = typeof body['error'] === 'string' ? body['error'] : `HTTP ${resp.status}`
      return
    }
    closePanel()
    await loadNodes()
  } catch (e) {
    formError.value = String(e)
  } finally {
    formLoading.value = false
  }
}

async function handleAddEdge(data: { source_id: string; target_id: string; conn_type: string }) {
  formLoading.value = true
  formError.value = null
  try {
    const resp = await fetch('/api/assurance/edges', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (resp.status === 423) { formError.value = 'Store is locked.'; return }
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({})) as Record<string, unknown>
      formError.value = typeof body['error'] === 'string' ? body['error'] : `HTTP ${resp.status}`
      return
    }
    panelMode.value = 'detail'
  } catch (e) {
    formError.value = String(e)
  } finally {
    formLoading.value = false
  }
}

// Initial data for the edit form from the selected node
const editInitialData = computed((): Partial<AssuranceNodeFormData> => {
  const n = selectedNode.value
  if (!n) return {}
  return {
    node_type: n.node_type,
    name: n.name,
    status: n.status ?? 'draft',
    tlp: n.tlp ?? 'TLP:WHITE',
    concern_class: n.concern_class ?? '',
    binding_status: n.binding_status ?? '',
  }
})

//: Authoring only. Detail has its own page, so the panel opens for create/edit/add-edge and
//: closes the moment those finish — the list is never squeezed just to read something.
const showPanel = computed(() => panelMode.value !== 'detail')

onMounted(() => {
  // `?node_id=` used to open the side panel, and links to it are still in the wild — the graph
  // explorer's "back to browse" among them. Now that a node has a page, honour the intent and
  // send the reader there rather than silently ignoring the parameter.
  const qNodeId = route.query['node_id']
  if (typeof qNodeId === 'string' && qNodeId) {
    void router.replace({ path: `/assurance/node/${qNodeId}` })
    return
  }
  void loadNodes()
})

// Reload the node list whenever the analysis scope changes.
watch(analysisId, () => { void loadNodes() })
</script>

<template>
  <div class="browse-page">
    <!-- The store's lock state, above the content it gates; silent when unlocked. -->
    <AssuranceStoreStatus />

    <div class="browse-header">
      <div class="browse-title-row">
        <h1 class="browse-title">
          Assurance nodes
        </h1>
        <div class="browse-header-actions">
          <button
            class="btn-create"
            type="button"
            @click="openCreate"
          >
            + New node
          </button>
          <button
            class="reload-btn"
            type="button"
            :disabled="loading"
            @click="loadNodes"
          >
            {{ loading ? 'Loading…' : '↺ Refresh' }}
          </button>
        </div>
      </div>
      <div class="browse-analysis-row">
        <AssuranceAnalysisPicker
          :model-value="analysisId"
          @update:model-value="setAnalysis"
        />
      </div>
      <WithheldNotice
        v-if="visibilityLimited"
        kind="nodes"
      />
    </div>

    <div
      v-if="error"
      class="browse-error"
    >
      {{ error }}
    </div>

    <div
      v-else
      class="browse-body"
      :class="{ 'browse-body--split': showPanel }"
    >
      <AssuranceWizardNav :selected-analysis-id="analysisScope" />

      <!-- Filter + list panel -->
      <AssuranceNodeList
        v-model:selection="filters"
        v-model:sort-key="sortKey"
        v-model:sort-dir="sortDir"
        :rows="filtered"
        :columns="BROWSE_COLUMNS"
        :filters="NODE_FILTERS"
        :options-for="optionsFor"
        :view-mode="viewMode"
        :loading="loading"
        :empty-message="emptyMessage"
        :selected-node-id="selectedNodeId"
        @set-view-mode="setViewMode"
        @sort="applySort"
        @select="selectNode"
      />

      <!-- Right panel: detail / create / edit / add-edge -->
      <div
        v-if="showPanel"
        class="browse-detail-panel"
      >
        <!-- Shared form error banner -->
        <div
          v-if="formError"
          class="panel-error"
        >
          {{ formError }}
        </div>

        <!-- CREATE -->
        <div
          v-if="panelMode === 'create'"
          class="panel-section"
        >
          <div class="panel-header">
            <h2 class="panel-title">
              New assurance node
            </h2>
            <button
              class="panel-close"
              type="button"
              aria-label="Close"
              @click="closePanel"
            >
              ×
            </button>
          </div>
          <div class="panel-body">
            <AssuranceNodeForm
              :loading="formLoading"
              @submit="handleCreate"
              @cancel="closePanel"
            />
          </div>
        </div>

        <!-- EDIT -->
        <div
          v-else-if="panelMode === 'edit' && selectedNode"
          class="panel-section"
        >
          <div class="panel-header">
            <h2 class="panel-title">
              Edit node
            </h2>
            <button
              class="panel-close"
              type="button"
              aria-label="Close"
              @click="backToDetail"
            >
              ×
            </button>
          </div>
          <div class="panel-body">
            <AssuranceNodeForm
              :initial-data="editInitialData"
              :locked-node-type="selectedNode.node_type"
              :loading="formLoading"
              @submit="handleEdit"
              @cancel="backToDetail"
            />
          </div>
        </div>

        <!-- ADD EDGE -->
        <div
          v-else-if="panelMode === 'add-edge' && selectedNode"
          class="panel-section"
        >
          <div class="panel-header">
            <h2 class="panel-title">
              Add edge from node
            </h2>
            <button
              class="panel-close"
              type="button"
              aria-label="Close"
              @click="backToDetail"
            >
              ×
            </button>
          </div>
          <div class="panel-body">
            <AssuranceEdgePicker
              :source-id="selectedNode.node_id"
              :source-type="selectedNode.node_type"
              :source-analysis-id="selectedNode.analysis_id ?? null"
              :loading="formLoading"
              @submit="handleAddEdge"
              @cancel="backToDetail"
            />
          </div>
        </div>

        <!-- DETAIL -->
        <div
          v-else-if="selectedNodeId"
          class="panel-section"
        >
          <div class="panel-header">
            <div class="panel-detail-actions">
              <button
                class="btn-edit"
                type="button"
                @click="openEdit"
              >
                Edit
              </button>
              <button
                class="btn-add-edge"
                type="button"
                @click="openAddEdge"
              >
                Add edge
              </button>
              <button
                class="btn-delete"
                type="button"
                :disabled="formLoading"
                @click="handleDelete"
              >
                Delete
              </button>
            </div>
            <button
              class="panel-close"
              type="button"
              aria-label="Close"
              @click="closePanel"
            >
              ×
            </button>
          </div>
          <AssuranceNodeDetail
            :node-id="selectedNodeId"
            @close="closePanel"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.browse-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.browse-header {
  padding: 20px 24px 16px;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
}
.browse-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.browse-title { font-size: 20px; font-weight: 700; margin: 0; }
.browse-header-actions { display: flex; gap: 8px; }
.btn-create {
  padding: 6px 14px;
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-create:hover { background: #1d4ed8; }
.reload-btn {
  padding: 5px 12px;
  border-radius: 6px;
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
  font-size: 13px;
  cursor: pointer;
}
.reload-btn:hover:not(:disabled) { background: #e5e7eb; }
.reload-btn:disabled { opacity: 0.5; cursor: default; }
.browse-analysis-row { margin-top: 10px; }
.visibility-note { font-size: 12px; color: #9ca3af; margin: 6px 0 0; }
.browse-error {
  padding: 24px;
  color: #b91c1c;
  background: #fef2f2;
  border-radius: 8px;
  margin: 16px 24px;
  font-size: 14px;
}
.browse-body { display: flex; flex: 1; overflow: hidden; }
.browse-list-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid #e2e8f0;
  min-width: 0;
}
.browse-body--split .browse-list-panel { max-width: 400px; }
.browse-detail-panel { flex: 1; overflow: hidden; min-width: 0; display: flex; flex-direction: column; }
.panel-error {
  padding: 8px 16px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 13px;
  border-bottom: 1px solid #fca5a5;
  flex-shrink: 0;
}
.panel-section { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
}
.panel-title { font-size: 15px; font-weight: 600; margin: 0; }
.panel-body { flex: 1; overflow-y: auto; padding: 16px; }
.panel-close {
  background: none;
  border: none;
  font-size: 18px;
  color: #9ca3af;
  cursor: pointer;
  padding: 2px 6px;
  line-height: 1;
}
.panel-close:hover { color: #374151; }
.panel-detail-actions { display: flex; gap: 8px; }
.btn-edit, .btn-add-edge, .btn-delete {
  padding: 5px 12px;
  border-radius: 5px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid;
}
.btn-edit { background: #f0f9ff; color: #0369a1; border-color: #bae6fd; }
.btn-edit:hover { background: #e0f2fe; }
.btn-add-edge { background: #f0fdf4; color: #15803d; border-color: #bbf7d0; }
.btn-add-edge:hover { background: #dcfce7; }
.btn-delete { background: #fef2f2; color: #b91c1c; border-color: #fca5a5; }
.btn-delete:hover:not(:disabled) { background: #fee2e2; }
.btn-delete:disabled { opacity: 0.5; cursor: default; }
.list-toolbar {
  display: flex; align-items: center; gap: 10px; padding: 8px 16px 0;
}
.view-toggle { display: inline-flex; gap: 4px; }
.toggle-btn {
  font-size: 11.5px; padding: 3px 10px; border: 1px solid #d1d5db; border-radius: 5px;
  background: white; cursor: pointer; color: #374151;
}
.toggle-btn:hover:not(.toggle-btn--active) { background: #f3f4f6; }
/* Selected keeps its own colours through hover, as elsewhere: a bare :hover rule would
   otherwise restore the pale background while the white label stayed. */
.toggle-btn--active { background: #2563eb; color: white; border-color: #2563eb; }
.toggle-btn--active:hover { background: #1d4ed8; }

.node-name--link { color: #1d4ed8; text-decoration: none; }
.node-name--link:hover { text-decoration: underline; }
.node-status, .node-concern { font-size: 11.5px; color: #374151; }
/* The direction breakdown reads as a gloss on the total, not a second number. */
.conn-split { margin-left: 6px; font-size: 11px; color: #6b7280; }

.list-count { padding: 6px 16px; font-size: 12px; color: #6b7280; border-bottom: 1px solid #f1f5f9; flex-shrink: 0; }
.list-loading { padding: 24px 16px; color: #6b7280; font-size: 14px; }
.node-table-scroll { overflow-y: auto; flex: 1; }
.stamp { font-size: 12px; color: #6b7280; white-space: nowrap; }
.node-type-badge {
  font-size: 11px;
  font-weight: 500;
  background: #dbeafe;
  color: #1d4ed8;
  padding: 2px 7px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}
.node-name { font-weight: 500; }
.node-tlp { font-size: 11px; font-weight: 600; }
.node-binding { font-size: 11px; padding: 1px 6px; border-radius: 3px; }
.node-binding--bound { background: #dcfce7; color: #15803d; }
.node-binding--unbound { background: #fee2e2; color: #b91c1c; }
</style>
