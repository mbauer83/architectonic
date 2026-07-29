<script setup lang="ts">
import { ref } from 'vue'
import type { MatrixConnTypeConfig } from '../composables/useMatrixEditor'

interface Props {
  connTypeConfigs: MatrixConnTypeConfig[]
  connCountsByType: Record<string, number>
}
const props = defineProps<Props>()
const emit = defineEmits<{
  toggle: [connType: string]
  reorder: [from: number, to: number]
}>()

const dragFromIdx = ref<number | null>(null)
const dragOverIdx = ref<number | null>(null)

const onDragStart = (idx: number, e: DragEvent) => {
  dragFromIdx.value = idx
  e.dataTransfer?.setData('text/plain', String(idx))
}
const onDragOver = (idx: number, e: DragEvent) => {
  e.preventDefault()
  dragOverIdx.value = idx
}
const onDrop = (toIdx: number, e: DragEvent) => {
  e.preventDefault()
  if (dragFromIdx.value !== null && dragFromIdx.value !== toIdx) {
    emit('reorder', dragFromIdx.value, toIdx)
  }
  dragFromIdx.value = null
  dragOverIdx.value = null
}
const onDragEnd = () => {
  dragFromIdx.value = null
  dragOverIdx.value = null
}
</script>

<template>
  <div class="conn-list">
    <div
      v-if="props.connTypeConfigs.length === 0"
      class="empty"
    >
      No connection types discovered yet.
    </div>
    <div
      v-for="(cfg, idx) in props.connTypeConfigs"
      :key="cfg.conn_type"
      class="conn-row"
      :class="{ 'drag-over': dragOverIdx === idx, 'inactive': !cfg.active }"
      draggable="true"
      @dragstart="onDragStart(idx, $event)"
      @dragover="onDragOver(idx, $event)"
      @drop="onDrop(idx, $event)"
      @dragend="onDragEnd"
    >
      <span
        class="drag-handle"
        title="Drag to reorder"
      >⠿</span>
      <input
        type="checkbox"
        :checked="cfg.active"
        class="toggle"
        @change="emit('toggle', cfg.conn_type)"
      >
      <span class="conn-type-name">{{ cfg.conn_type }}</span>
      <span
        v-if="(props.connCountsByType[cfg.conn_type] ?? 0) > 0"
        class="count-badge"
      >
        {{ props.connCountsByType[cfg.conn_type] }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.conn-list { display: flex; flex-direction: column; gap: 2px; }
.empty { color: #9ca3af; font-size: 13px; padding: 8px 0; }
.conn-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; border: 1px solid #e5e7eb; border-radius: 6px;
  background: white; cursor: grab;
}
.conn-row.drag-over { border-color: #2563eb; background: #eff6ff; }
.conn-row.inactive { opacity: 0.5; }
.drag-handle { color: #9ca3af; font-size: 14px; cursor: grab; flex-shrink: 0; }
.toggle { cursor: pointer; flex-shrink: 0; }
.conn-type-name { flex: 1; font-size: 13px; color: #1e293b; font-family: monospace; }
.count-badge {
  font-size: 11px; padding: 1px 6px; border-radius: 10px;
  background: #dbeafe; color: #1e40af; font-weight: 600;
}
</style>
