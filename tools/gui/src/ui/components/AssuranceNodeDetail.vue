<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import ModelThisPanel from './ModelThisPanel.vue'
import AssuranceEdgeList from './AssuranceEdgeList.vue'
import AssuranceProvenance from './AssuranceProvenance.vue'
import { provenanceOf, type AssuranceProvenanceFields } from './AssuranceProvenance.helpers'
import type { AssuranceEdge } from './AssuranceNodeDetail.helpers'
import { isUnboundControlNode } from './ModelThisPanel.helpers'
import { tlpColor } from './tlp'

const props = defineProps<{ nodeId: string | null }>()
const emit = defineEmits<{
  close: []
  loadState: [state: 'ok' | 'not-found' | 'locked' | 'error']
}>()

interface ArchRef {
  arch_artifact_id: string
  relationship_type?: string
  notes?: string
}

type Edge = AssuranceEdge

interface NodeDetail {
  node_id: string
  node_type: string
  name: string
  status?: string
  tlp?: string
  concern_class?: string
  disposition?: string
  uca_type?: string
  binding_status?: string
  node_role?: string
  content_text?: string
  attributes?: Record<string, unknown>
}

interface NodeResponse extends Partial<AssuranceProvenanceFields> {
  node: NodeDetail
  outgoing_edges: Edge[]
  incoming_edges: Edge[]
  arch_refs: ArchRef[]
}

const data = ref<NodeResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

async function load(nodeId: string | null) {
  if (!nodeId) { data.value = null; return }
  loading.value = true
  error.value = null
  try {
    const resp = await fetch(`/api/assurance/nodes/${encodeURIComponent(nodeId)}`)
    if (resp.status === 423) { error.value = 'Store locked'; emit('loadState', 'locked'); return }
    // Absent and above-ceiling are indistinguishable by design (same 404).
    if (resp.status === 404) { error.value = 'Node not found'; emit('loadState', 'not-found'); return }
    if (!resp.ok) { error.value = `HTTP ${resp.status}`; emit('loadState', 'error'); return }
    data.value = await resp.json() as NodeResponse
    emit('loadState', 'ok')
  } catch (e) {
    error.value = String(e)
    emit('loadState', 'error')
  } finally {
    loading.value = false
  }
}

watch(() => props.nodeId, load, { immediate: true })

function archEntityPath(ref: ArchRef): string {
  return `/entity?id=${encodeURIComponent(ref.arch_artifact_id)}`
}

const deletingEdgeId = ref<string | null>(null)

async function deleteEdge(edge: Edge) {
  if (!edge.edge_id || deletingEdgeId.value) return
  deletingEdgeId.value = edge.edge_id
  try {
    const resp = await fetch(`/api/assurance/edges/${encodeURIComponent(edge.edge_id)}`, { method: 'DELETE' })
    if (resp.ok) await load(props.nodeId)
    else error.value = `Delete failed: HTTP ${resp.status}`
  } catch (e) {
    error.value = String(e)
  } finally {
    deletingEdgeId.value = null
  }
}
</script>

<template>
  <div class="node-detail">
    <div class="detail-hdr">
      <span class="detail-title">Node detail</span>
      <RouterLink
        v-if="data"
        :to="{ path: '/assurance/graph', query: { node_id: data.node.node_id } }"
        class="explore-link"
      >
        Explore graph
      </RouterLink>
      <button
        class="close-btn"
        type="button"
        aria-label="Close"
        @click="emit('close')"
      >
        ×
      </button>
    </div>

    <div
      v-if="loading"
      class="detail-loading"
    >
      Loading…
    </div>
    <div
      v-else-if="error"
      class="detail-error"
    >
      {{ error }}
    </div>
    <template v-else-if="data">
      <!-- Identity -->
      <div class="detail-section">
        <div class="detail-row">
          <span class="detail-label">Name</span>
          <RouterLink
            :to="`/assurance/node/${encodeURIComponent(data.node.node_id)}`"
            class="detail-value"
          >
            {{ data.node.name }}
          </RouterLink>
        </div>
        <div class="detail-row">
          <span class="detail-label">Type</span>
          <span class="detail-badge">{{ data.node.node_type }}</span>
        </div>
        <div
          v-if="data.node.status"
          class="detail-row"
        >
          <span class="detail-label">Status</span>
          <span class="detail-value">{{ data.node.status }}</span>
        </div>
        <div
          v-if="data.node.tlp"
          class="detail-row"
        >
          <span class="detail-label">TLP</span>
          <span
            class="detail-value tlp-value"
            :style="{ color: tlpColor(data.node.tlp) }"
          >{{ data.node.tlp }}</span>
        </div>
        <div
          v-if="data.node.concern_class"
          class="detail-row"
        >
          <span class="detail-label">Concern</span>
          <span class="detail-value">{{ data.node.concern_class }}</span>
        </div>
        <div
          v-if="data.node.disposition"
          class="detail-row"
        >
          <span class="detail-label">Disposition</span>
          <span class="detail-value">{{ data.node.disposition }}</span>
        </div>
        <div
          v-if="data.node.binding_status"
          class="detail-row"
        >
          <span class="detail-label">Binding</span>
          <span class="detail-value">{{ data.node.binding_status }}</span>
        </div>
        <div
          v-if="data.node.uca_type"
          class="detail-row"
        >
          <span class="detail-label">UCA type</span>
          <span class="detail-value">{{ data.node.uca_type }}</span>
        </div>
      </div>

      <!-- Provenance: authored here, or borrowed from another analysis. A borrowed entity has
           to look borrowed, or the combined analysis silently claims another method's work. -->
      <AssuranceProvenance
        :authored-by="provenanceOf(data).authored_by"
        :participates-in="provenanceOf(data).participates_in"
      />

      <!-- Modelling gap: model-this affordance for unbound control-structure nodes -->
      <div
        v-if="isUnboundControlNode(data.node.node_type, data.node.binding_status)"
        class="detail-section"
      >
        <ModelThisPanel
          :node-id="data.node.node_id"
          :node-name="data.node.name"
          @bound="load(props.nodeId)"
        />
      </div>

      <!-- Content -->
      <div
        v-if="data.node.content_text"
        class="detail-section"
      >
        <p class="detail-content">
          {{ data.node.content_text }}
        </p>
      </div>

      <!-- Architecture references -->
      <div
        v-if="data.arch_refs.length > 0"
        class="detail-section"
      >
        <div class="section-label">
          Architecture references
        </div>
        <ul class="ref-list">
          <li
            v-for="archRef in data.arch_refs"
            :key="archRef.arch_artifact_id"
            class="ref-item"
          >
            <RouterLink
              :to="archEntityPath(archRef)"
              class="ref-link"
            >
              <span class="ref-icon">↗</span>
              <span class="ref-id">{{ archRef.arch_artifact_id }}</span>
            </RouterLink>
            <span
              v-if="archRef.relationship_type"
              class="ref-rel"
            >{{ archRef.relationship_type }}</span>
          </li>
        </ul>
      </div>

      <!-- Edges -->
      <AssuranceEdgeList
        label="Outgoing"
        :edges="data.outgoing_edges"
        direction="outgoing"
        :deleting="deletingEdgeId !== null"
        @delete="deleteEdge"
      />
      <AssuranceEdgeList
        label="Incoming"
        :edges="data.incoming_edges"
        direction="incoming"
        :deleting="deletingEdgeId !== null"
        @delete="deleteEdge"
      />
    </template>
  </div>
</template>

<style scoped src="./AssuranceNodeDetail.css"></style>
