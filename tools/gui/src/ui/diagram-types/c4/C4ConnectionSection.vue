<script setup lang="ts">
import { ref } from 'vue'
import type { DiagramConnection } from '../../../domain'

const props = defineProps<{
  items: Array<{ id: string; label: string; itemType: string }>
  diagramConnections: DiagramConnection[]
}>()
const emit = defineEmits<{ diagramConnectionsChange: [DiagramConnection[]] }>()

const addingConnection = ref(false)
const newSource = ref('')
const newTarget = ref('')
const newLabel = ref('')

const addConnection = () => {
  if (!newSource.value || !newTarget.value) return
  const srcItem = props.items.find((i) => i.id === newSource.value)
  const tgtItem = props.items.find((i) => i.id === newTarget.value)
  const conn: DiagramConnection = {
    artifact_id: `c4-uses-${Date.now()}`,
    source: newSource.value,
    target: newTarget.value,
    conn_type: 'c4-uses',
    version: '0.1.0',
    status: 'draft',
    path: '',
    content_text: newLabel.value,
    source_name: srcItem?.label ?? newSource.value,
    target_name: tgtItem?.label ?? newTarget.value,
    source_alias: null,
    target_alias: null,
  }
  emit('diagramConnectionsChange', [...props.diagramConnections, conn])
  newSource.value = ''
  newTarget.value = ''
  newLabel.value = ''
  addingConnection.value = false
}

const removeConnection = (artifactId: string) => {
  emit('diagramConnectionsChange', props.diagramConnections.filter((c) => c.artifact_id !== artifactId))
}
</script>

<template>
  <section class="conn-section">
    <div class="conn-hdr">
      <span class="conn-title">Connections</span>
      <span class="conn-hint">c4-uses relationships between diagram items</span>
      <button
        class="add-btn"
        type="button"
        @click="addingConnection = !addingConnection"
      >
        {{ addingConnection ? 'Cancel' : '+ Add' }}
      </button>
    </div>

    <!-- Add connection form -->
    <div
      v-if="addingConnection"
      class="add-form"
    >
      <select
        v-model="newSource"
        class="conn-select"
      >
        <option
          value=""
          :disabled="true"
        >
          From…
        </option>
        <option
          v-for="item in items"
          :key="item.id"
          :value="item.id"
        >
          {{ item.label }} ({{ item.itemType }})
        </option>
      </select>
      <span class="arrow">→</span>
      <select
        v-model="newTarget"
        class="conn-select"
      >
        <option
          value=""
          :disabled="true"
        >
          To…
        </option>
        <option
          v-for="item in items"
          :key="item.id"
          :value="item.id"
        >
          {{ item.label }} ({{ item.itemType }})
        </option>
      </select>
      <input
        v-model="newLabel"
        class="label-input"
        type="text"
        placeholder="Label (optional)"
        @keyup.enter="addConnection"
      >
      <button
        class="confirm-btn"
        type="button"
        :disabled="!newSource || !newTarget"
        @click="addConnection"
      >
        Add
      </button>
    </div>

    <!-- Existing connections -->
    <div
      v-if="diagramConnections.length"
      class="conn-list"
    >
      <div
        v-for="conn in diagramConnections"
        :key="conn.artifact_id"
        class="conn-row"
      >
        <span class="conn-src">{{ conn.source_name || conn.source }}</span>
        <span class="conn-arrow">→</span>
        <span class="conn-tgt">{{ conn.target_name || conn.target }}</span>
        <span
          v-if="conn.content_text"
          class="conn-label"
        >{{ conn.content_text }}</span>
        <button
          class="remove-btn"
          type="button"
          @click="removeConnection(conn.artifact_id)"
        >
          ✕
        </button>
      </div>
    </div>
    <div
      v-else-if="!addingConnection"
      class="conn-empty"
    >
      No connections yet.
    </div>
  </section>
</template>

<style scoped>
.conn-section {
  display: flex; flex-direction: column; gap: 8px;
  padding: 12px; border: 1px solid #e2e8f0; border-radius: 8px; background: #f8fafc;
}
.conn-hdr { display: flex; align-items: center; gap: 8px; }
.conn-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #374151; }
.conn-hint { font-size: 11px; color: #9ca3af; flex: 1; }
.add-btn { padding: 3px 10px; font-size: 12px; border: 1px solid #d1d5db; border-radius: 6px; background: white; cursor: pointer; color: #374151; }
.add-btn:hover { background: #f9fafb; }
.add-form { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 8px; background: white; border: 1px solid #e2e8f0; border-radius: 6px; }
.conn-select { flex: 1; min-width: 120px; padding: 4px 6px; font-size: 12px; border: 1px solid #d1d5db; border-radius: 4px; }
.arrow { font-size: 14px; color: #6b7280; flex-shrink: 0; }
.label-input { flex: 1; min-width: 100px; padding: 4px 6px; font-size: 12px; border: 1px solid #d1d5db; border-radius: 4px; }
.confirm-btn { padding: 4px 12px; font-size: 12px; border: 1px solid #3b82f6; border-radius: 6px; background: #3b82f6; color: white; cursor: pointer; }
.confirm-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.confirm-btn:not(:disabled):hover { background: #2563eb; }
.conn-list { display: flex; flex-direction: column; gap: 4px; }
.conn-row { display: flex; align-items: center; gap: 6px; padding: 6px 8px; background: white; border: 1px solid #e2e8f0; border-radius: 4px; font-size: 12px; }
.conn-src, .conn-tgt { font-weight: 500; color: #1e293b; }
.conn-arrow { color: #9ca3af; }
.conn-label { color: #6b7280; font-style: italic; flex: 1; }
.remove-btn { margin-left: auto; padding: 2px 6px; font-size: 11px; border: 1px solid #fca5a5; border-radius: 4px; background: white; color: #dc2626; cursor: pointer; }
.remove-btn:hover { background: #fef2f2; }
.conn-empty { font-size: 12px; color: #9ca3af; padding: 4px 2px; }
</style>
