<script setup lang="ts">
import type { StepNote } from './activityElementMapping'

const props = defineProps<{ note?: StepNote | null }>()
const emit = defineEmits<{ update: [note: StepNote | null] }>()

const set = (patch: Partial<StepNote>) => {
  const note = props.note
  if (!note) return
  const next: StepNote = { side: patch.side ?? note.side, text: patch.text ?? note.text }
  emit('update', next)
}
</script>

<template>
  <div class="ns">
    <template v-if="note">
      <div class="ns-hdr">
        <select
          class="ns-side"
          :value="note.side"
          @change="set({ side: ($event.target as HTMLSelectElement).value })"
        >
          <option value="right">
            Note right
          </option>
          <option value="left">
            Note left
          </option>
        </select>
        <button
          class="ns-rm"
          type="button"
          @click="emit('update', null)"
        >
          × Remove note
        </button>
      </div>
      <textarea
        class="ns-text"
        rows="2"
        placeholder="Note text…"
        :value="note.text"
        @input="set({ text: ($event.target as HTMLTextAreaElement).value })"
      />
    </template>
    <button
      v-else
      class="ns-add"
      type="button"
      @click="emit('update', { side: 'right', text: '' })"
    >
      + Note
    </button>
  </div>
</template>

<style scoped>
.ns { display: flex; flex-direction: column; gap: 4px; }
.ns-hdr { display: flex; align-items: center; gap: 6px; }
.ns-side { padding: 3px 5px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 12px; background: #fffbeb; }
.ns-rm { font-size: 11px; color: #9ca3af; background: none; border: 1px solid #e2e8f0; border-radius: 4px; padding: 2px 6px; cursor: pointer; }
.ns-rm:hover { color: #ef4444; border-color: #fca5a5; }
.ns-text { width: 100%; resize: vertical; font-family: inherit; font-size: 12px; padding: 4px 6px; border: 1px solid #fde68a; border-radius: 4px; background: #fffbeb; box-sizing: border-box; }
.ns-add { font-size: 11px; color: #92400e; background: none; border: 1px dashed #fde68a; border-radius: 4px; padding: 2px 7px; cursor: pointer; align-self: flex-start; }
.ns-add:hover { background: #fffbeb; }
</style>
