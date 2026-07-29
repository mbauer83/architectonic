<script setup lang="ts">
import { ref } from 'vue'
import type { Lifeline, Message } from './useSequenceModel'
import MessageRow from './MessageRow.vue'

const props = defineProps<{
  messages: Message[]
  lifelines: Lifeline[]
  fromMap: Map<string, string>
  toMap: Map<string, string>
}>()
const emit = defineEmits<{
  add: []
  remove: [id: string]
  update: [{ id: string; patch: Partial<Message> }]
  setFrom: [{ msgId: string; lifelineId: string }]
  setTo: [{ msgId: string; lifelineId: string }]
  reorder: [newOrder: Message[]]
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
  const order = [...props.messages]
  const [item] = order.splice(from, 1)
  order.splice(targetIndex, 0, item)
  emit('reorder', order)
  dragIndex.value = null
}
</script>

<template>
  <section class="msg-list">
    <div class="msg-list-header">
      <span>Messages</span>
      <button
        class="mini-btn"
        type="button"
        :disabled="lifelines.length < 2"
        @click="emit('add')"
      >
        +
      </button>
    </div>
    <p
      v-if="lifelines.length < 2"
      class="list-hint"
    >
      Add at least two lifelines before adding messages.
    </p>
    <p
      v-else-if="messages.length === 0"
      class="list-hint"
    >
      Add messages to define the sequence flow.
    </p>
    <div
      v-for="(msg, i) in messages"
      :key="msg.id"
      class="msg-drag-wrapper"
      :class="{ 'drag-over': dragIndex !== null && dragIndex !== i }"
      draggable="true"
      @dragstart="onDragStart(i, $event)"
      @dragover="onDragOver"
      @drop="onDrop(i)"
    >
      <MessageRow
        :message="msg"
        :lifelines="lifelines"
        :from-id="fromMap.get(msg.id) ?? ''"
        :to-id="toMap.get(msg.id) ?? ''"
        :index="i"
        @update="emit('update', { id: msg.id, patch: $event })"
        @remove="emit('remove', msg.id)"
        @set-from="emit('setFrom', { msgId: msg.id, lifelineId: $event })"
        @set-to="emit('setTo', { msgId: msg.id, lifelineId: $event })"
      />
    </div>
  </section>
</template>

<style scoped>
.msg-list { display: flex; flex-direction: column; gap: 6px; }
.msg-list-header { display: flex; align-items: center; justify-content: space-between; font-weight: 650; font-size: 12px; }
.list-hint { font-size: 12px; color: #9ca3af; margin: 0; }
.msg-drag-wrapper { border-radius: 6px; }
.msg-drag-wrapper.drag-over { outline: 2px solid #93c5fd; outline-offset: 1px; }
.mini-btn { min-width: 24px; height: 24px; border: 1px solid #cbd5e1; background: #fff; border-radius: 5px; cursor: pointer; font-size: 14px; color: #374151; }
.mini-btn:disabled { opacity: .45; cursor: not-allowed; }
</style>
