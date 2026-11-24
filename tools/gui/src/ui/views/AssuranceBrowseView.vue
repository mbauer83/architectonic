<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AssuranceNodeDetail from '../components/AssuranceNodeDetail.vue'
import { assuranceNodeDetailRoute } from '../router/artifactRoutes'
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
const loading = ref(true)  // a view that loads on mount is loading from its first frame, not after it
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
  void router.push(assuranceNodeDetailRoute(nodeId))
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
    void router.replace(assuranceNodeDetailRoute(qNodeId))
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

<style scoped src="./AssuranceBrowseView.css"></style>
