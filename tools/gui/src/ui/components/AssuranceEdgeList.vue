<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { endpointLabel, groupByType, nodeBrowsePath } from './AssuranceNodeDetail.helpers'
import type { AssuranceEdge } from './AssuranceNodeDetail.helpers'

const props = defineProps<{
  label: string
  edges: AssuranceEdge[]
  direction: 'outgoing' | 'incoming'
  deleting: boolean
}>()
const emit = defineEmits<{ delete: [edge: AssuranceEdge] }>()

const grouped = computed(() => groupByType(props.edges))
const endpointEnd = computed(() => props.direction === 'outgoing' ? 'target' : 'source')

function endpointId(edge: AssuranceEdge): string {
  return props.direction === 'outgoing' ? edge.target_id : edge.source_id
}

function endpointType(edge: AssuranceEdge): string | undefined {
  return props.direction === 'outgoing' ? edge.target_type : edge.source_type
}
</script>

<template>
  <div
    v-if="edges.length > 0"
    class="detail-section"
  >
    <div class="section-label">
      {{ label }} ({{ edges.length }})
    </div>
    <div
      v-for="(group, typeKey) in grouped"
      :key="typeKey"
      class="edge-group"
    >
      <div class="edge-group-header">
        {{ typeKey }} ({{ group.length }})
      </div>
      <ul class="edge-list">
        <li
          v-for="edge in group"
          :key="edge.edge_id ?? endpointId(edge)"
          class="edge-item"
        >
          <span
            v-if="direction === 'outgoing'"
            class="edge-arrow"
          >→</span>
          <RouterLink
            :to="nodeBrowsePath(endpointId(edge))"
            class="edge-endpoint"
          >
            {{ endpointLabel(edge, endpointEnd) }}
          </RouterLink>
          <span
            v-if="endpointType(edge)"
            class="edge-node-type"
          >{{ endpointType(edge) }}</span>
          <span
            v-if="direction === 'incoming'"
            class="edge-arrow"
          >→</span>
          <button
            v-if="edge.edge_id"
            class="edge-delete-btn"
            title="Delete this connection"
            :disabled="deleting"
            @click="emit('delete', edge)"
          >
            ×
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.detail-section {
  padding: 12px 16px;
  border-bottom: 1px solid #f1f5f9;
}
.section-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #6b7280;
  margin-bottom: 8px;
}
.edge-group { margin-bottom: 6px; }
.edge-group-header {
  font-size: 11px;
  font-weight: 500;
  background: #f1f5f9;
  padding: 1px 5px;
  border-radius: 3px;
  color: #475569;
  display: inline-block;
  margin-bottom: 2px;
}
.edge-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.edge-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-family: monospace;
  color: #374151;
}
.edge-arrow { color: #9ca3af; }
.edge-endpoint {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #2563eb;
  text-decoration: none;
}
.edge-endpoint:hover { text-decoration: underline; }
.edge-node-type { font-size: 10px; color: #9ca3af; }
.edge-delete-btn {
  margin-left: auto;
  border: none;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  padding: 0 4px;
}
.edge-delete-btn:hover { color: #dc2626; }
.edge-delete-btn:disabled { cursor: default; opacity: 0.4; }
</style>
