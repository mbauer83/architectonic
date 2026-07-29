<script setup lang="ts">
import { ref } from 'vue'
import type { Lifeline, Message } from './useSequenceModel'

const ARROW_OPTIONS = [
  { value: 'sync',    label: 'sync' },
  { value: 'async',   label: 'async' },
  { value: 'reply',   label: 'reply' },
  { value: 'self',    label: 'self' },
  { value: 'create',  label: 'create' },
  { value: 'destroy', label: 'destroy' },
] as const

defineProps<{
  message: Message
  lifelines: Lifeline[]
  fromId: string
  toId: string
  index: number
}>()
const emit = defineEmits<{
  update: [patch: Partial<Message>]
  remove: []
  setFrom: [lifelineId: string]
  setTo: [lifelineId: string]
}>()

const expanded = ref(false)
const hasAdvanced = (m: Message) => m.activate_target || m.deactivate_target
</script>

<template>
  <div class="msg-row">
    <div class="msg-main">
      <div class="msg-order">
        <span
          class="drag-handle"
          title="Drag to reorder"
        >⠿</span>
        <span class="msg-idx">{{ index + 1 }}</span>
      </div>
      <select
        class="inp endpoint-sel"
        :value="fromId"
        @change="emit('setFrom', ($event.target as HTMLSelectElement).value)"
      >
        <option value="">
          from…
        </option>
        <option
          v-for="ll in lifelines"
          :key="ll.id"
          :value="ll.id"
        >
          {{ ll.label }}
        </option>
      </select>
      <select
        class="inp arrow-sel"
        :value="message.arrow || 'sync'"
        @change="emit('update', { arrow: ($event.target as HTMLSelectElement).value as Message['arrow'] })"
      >
        <option
          v-for="opt in ARROW_OPTIONS"
          :key="opt.value"
          :value="opt.value"
        >
          {{ opt.label }}
        </option>
      </select>
      <select
        class="inp endpoint-sel"
        :value="toId"
        @change="emit('setTo', ($event.target as HTMLSelectElement).value)"
      >
        <option value="">
          to…
        </option>
        <option
          v-for="ll in lifelines"
          :key="ll.id"
          :value="ll.id"
        >
          {{ ll.label }}
        </option>
      </select>
      <input
        class="inp msg-label"
        :value="message.label || ''"
        placeholder="label"
        @input="emit('update', { label: ($event.target as HTMLInputElement).value })"
      >
      <div class="msg-actions">
        <button
          class="adv-btn"
          :class="{ active: expanded || hasAdvanced(message) }"
          type="button"
          title="Advanced options"
          @click="expanded = !expanded"
        >
          ⚙
        </button>
        <button
          class="mini-btn rm-btn"
          type="button"
          title="Remove"
          @click="emit('remove')"
        >
          ×
        </button>
      </div>
    </div>
    <div
      v-if="expanded"
      class="msg-advanced"
    >
      <label class="adv-toggle">
        <input
          type="checkbox"
          :checked="!!message.activate_target"
          @change="emit('update', { activate_target: ($event.target as HTMLInputElement).checked })"
        >
        <span>Activate target (++)</span>
      </label>
      <label class="adv-toggle">
        <input
          type="checkbox"
          :checked="!!message.deactivate_target"
          @change="emit('update', { deactivate_target: ($event.target as HTMLInputElement).checked })"
        >
        <span>Deactivate target (--)</span>
      </label>
    </div>
    <div
      v-if="!fromId || !toId"
      class="msg-warn"
    >
      ⚠ Message missing {{ !fromId && !toId ? 'from and to' : !fromId ? 'from' : 'to' }} lifeline
    </div>
  </div>
</template>

<style scoped>
.msg-row { display: flex; flex-direction: column; gap: 4px; padding: 6px 8px; border: 1px solid #e2e8f0; border-radius: 6px; background: #fff; }
.msg-main { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.msg-order { display: flex; flex-direction: column; align-items: center; gap: 2px; flex-shrink: 0; }
.drag-handle { cursor: grab; color: #94a3b8; font-size: 14px; line-height: 1; }
.msg-idx { font-size: 10px; color: #94a3b8; }
.endpoint-sel { width: 100px; }
.arrow-sel { width: 90px; }
.msg-label { flex: 1; min-width: 80px; }
.msg-actions { display: flex; gap: 4px; flex-shrink: 0; }
.adv-btn { min-width: 24px; height: 24px; border: 1px solid #cbd5e1; background: #fff; border-radius: 5px; cursor: pointer; font-size: 12px; color: #94a3b8; }
.adv-btn.active { color: #2563eb; border-color: #93c5fd; background: #eff6ff; }
.mini-btn { min-width: 24px; height: 24px; border: 1px solid #cbd5e1; background: #fff; border-radius: 5px; cursor: pointer; font-size: 14px; color: #374151; }
.msg-advanced { display: flex; gap: 16px; padding: 4px 8px; background: #f8fafc; border-radius: 4px; }
.adv-toggle { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #475569; cursor: pointer; }
.msg-warn { font-size: 11px; color: #f59e0b; }
.inp {
  padding: 4px 6px; border: 1px solid #cbd5e1; border-radius: 5px;
  font-size: 12px; background: white; color: #1e293b; outline: none; box-sizing: border-box;
}
.inp:focus { border-color: #3b82f6; box-shadow: 0 0 0 2px #bfdbfe; }
</style>
