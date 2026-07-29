<script setup lang="ts">
import { ref } from 'vue'
import type { EntityDisplayInfo } from '../../../domain'
import ActivityEntityPicker from '../activity/ActivityEntityPicker.vue'
import type { Lifeline } from './useSequenceModel'

const PARTICIPANT_TYPES = ['participant', 'actor', 'boundary', 'control', 'entity', 'database', 'queue'] as const

const props = defineProps<{
  lifelines: Lifeline[]
  entities: EntityDisplayInfo[]
}>()
const emit = defineEmits<{
  add: []
  remove: [id: string]
  update: [{ id: string; patch: Partial<Lifeline> }]
  reorder: [newOrder: Lifeline[]]
}>()

const dragIndex = ref<number | null>(null)

function onDragStart(i: number, e: DragEvent) {
  dragIndex.value = i
  e.dataTransfer?.setData('text/plain', String(i))
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
}

function onDrop(targetIndex: number) {
  const from = dragIndex.value
  if (from === null || from === targetIndex) { dragIndex.value = null; return }
  const order = [...props.lifelines]
  const [item] = order.splice(from, 1)
  order.splice(targetIndex, 0, item)
  emit('reorder', order)
  dragIndex.value = null
}
</script>

<template>
  <section class="ll-strip">
    <div class="ll-header">
      <span>Lifelines</span>
      <button
        class="mini-btn"
        type="button"
        @click="emit('add')"
      >
        +
      </button>
    </div>
    <p
      v-if="lifelines.length === 0"
      class="ll-empty"
    >
      Add lifelines to define the participants.
    </p>
    <div class="ll-list">
      <div
        v-for="(ll, i) in lifelines"
        :key="ll.id"
        class="ll-card"
        :class="{ 'drag-over': dragIndex !== null && dragIndex !== i }"
        draggable="true"
        @dragstart="onDragStart(i, $event)"
        @dragover="onDragOver"
        @drop="onDrop(i)"
      >
        <div class="ll-card-top">
          <span
            class="drag-handle"
            title="Drag to reorder"
          >⠿</span>
          <input
            class="inp ll-label"
            :value="ll.label"
            placeholder="Label"
            @input="emit('update', { id: ll.id, patch: { label: ($event.target as HTMLInputElement).value } })"
          >
          <select
            class="inp ll-type"
            :value="ll.participant_type || 'participant'"
            @change="emit('update', { id: ll.id, patch: { participant_type: ($event.target as HTMLSelectElement).value } })"
          >
            <option
              v-for="pt in PARTICIPANT_TYPES"
              :key="pt"
              :value="pt"
            >
              {{ pt }}
            </option>
          </select>
          <button
            class="mini-btn rm-btn"
            type="button"
            title="Remove"
            @click="emit('remove', ll.id)"
          >
            ×
          </button>
        </div>
        <ActivityEntityPicker
          :entity-id="ll.entity_id"
          :accepted-types="['role', 'business-actor', 'application-component', 'application-service', 'node']"
          @pick="(id) => emit('update', { id: ll.id, patch: { entity_id: id ?? undefined } })"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.ll-strip { display: flex; flex-direction: column; gap: 8px; }
.ll-header { display: flex; align-items: center; justify-content: space-between; font-weight: 650; font-size: 12px; }
.ll-empty { font-size: 12px; color: #9ca3af; margin: 0; }
.ll-list { display: flex; flex-direction: column; gap: 6px; }
.ll-card {
  display: flex; flex-direction: column; gap: 6px; padding: 8px 10px;
  border: 1px solid #dbe3ef; border-radius: 8px; background: #fff; cursor: default;
}
.ll-card.drag-over { border-color: #3b82f6; }
.ll-card-top { display: flex; align-items: center; gap: 4px; }
.drag-handle { cursor: grab; color: #94a3b8; font-size: 14px; flex-shrink: 0; }
.ll-label { flex: 1; min-width: 0; }
.ll-type { width: 90px; flex-shrink: 0; font-size: 11px; }
.rm-btn { flex-shrink: 0; }
.mini-btn {
  min-width: 24px; height: 24px; border: 1px solid #cbd5e1; background: #fff;
  border-radius: 5px; cursor: pointer; font-size: 14px; color: #374151;
}
.mini-btn:hover { background: #f1f5f9; }
.inp {
  padding: 4px 7px; border: 1px solid #cbd5e1; border-radius: 5px;
  font-size: 12px; background: white; color: #1e293b; outline: none; box-sizing: border-box;
}
.inp:focus { border-color: #3b82f6; box-shadow: 0 0 0 2px #bfdbfe; }
</style>
