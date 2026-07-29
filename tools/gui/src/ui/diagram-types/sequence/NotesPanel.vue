<script setup lang="ts">
import type { Lifeline, Message, Note } from './useSequenceModel'

const PLACEMENT_OPTIONS = [
  { value: 'right_of', label: 'Right of' },
  { value: 'left_of', label: 'Left of' },
  { value: 'over', label: 'Over' },
] as const

const props = defineProps<{
  notes: Note[]
  lifelines: Lifeline[]
  messages: Message[]
}>()
const emit = defineEmits<{
  add: []
  remove: [id: string]
  update: [{ id: string; patch: Partial<Note> }]
}>()

function msgLabel(msgId: string) {
  const idx = props.messages.findIndex((m) => m.id === msgId)
  const m = props.messages[idx]
  return m ? `${idx + 1}. ${m.label || '(unlabelled)'}` : msgId
}

function isLifelineSelected(note: Note, llId: string) {
  return note.lifeline_ids.includes(llId)
}

function toggleLifeline(note: Note, llId: string) {
  const placement = note.placement ?? 'right_of'
  if (placement !== 'over') {
    emit('update', { id: note.id, patch: { lifeline_ids: [llId] } })
    return
  }
  const ids = note.lifeline_ids.includes(llId)
    ? note.lifeline_ids.filter((id) => id !== llId)
    : [...note.lifeline_ids, llId]
  if (ids.length > 0) emit('update', { id: note.id, patch: { lifeline_ids: ids } })
}
</script>

<template>
  <section class="notes-panel">
    <div class="notes-header">
      <span>Notes</span>
      <button
        class="mini-btn"
        type="button"
        :disabled="lifelines.length === 0"
        @click="emit('add')"
      >
        +
      </button>
    </div>
    <p
      v-if="notes.length === 0"
      class="list-hint"
    >
      Add notes to annotate lifelines or message positions.
    </p>
    <div
      v-for="note in notes"
      :key="note.id"
      class="note-card"
    >
      <div class="note-top">
        <select
          class="inp place-sel"
          :value="note.placement || 'right_of'"
          @change="emit('update', { id: note.id, patch: { placement: ($event.target as HTMLSelectElement).value as Note['placement'] } })"
        >
          <option
            v-for="p in PLACEMENT_OPTIONS"
            :key="p.value"
            :value="p.value"
          >
            {{ p.label }}
          </option>
        </select>
        <button
          class="mini-btn rm-btn"
          type="button"
          title="Remove note"
          @click="emit('remove', note.id)"
        >
          ×
        </button>
      </div>
      <textarea
        class="inp note-text"
        :value="note.text"
        placeholder="Note text…"
        rows="2"
        @input="emit('update', { id: note.id, patch: { text: ($event.target as HTMLTextAreaElement).value } })"
      />
      <div class="ll-select">
        <span class="field-label">Lifeline{{ (note.placement ?? 'right_of') === 'over' ? 's' : '' }}:</span>
        <button
          v-for="ll in lifelines"
          :key="ll.id"
          class="ll-chip"
          :class="{ selected: isLifelineSelected(note, ll.id) }"
          type="button"
          @click="toggleLifeline(note, ll.id)"
        >
          {{ ll.label }}
        </button>
      </div>
      <div class="anchor-row">
        <span class="field-label">After message:</span>
        <select
          class="inp anchor-sel"
          :value="note.after_message_id || ''"
          @change="emit('update', { id: note.id, patch: { after_message_id: ($event.target as HTMLSelectElement).value || undefined } })"
        >
          <option value="">
            end of diagram
          </option>
          <option
            v-for="m in messages"
            :key="m.id"
            :value="m.id"
          >
            {{ msgLabel(m.id) }}
          </option>
        </select>
      </div>
    </div>
  </section>
</template>

<style scoped>
.notes-panel { display: flex; flex-direction: column; gap: 8px; }
.notes-header { display: flex; align-items: center; justify-content: space-between; font-weight: 650; font-size: 12px; }
.list-hint { font-size: 12px; color: #9ca3af; margin: 0; }
.note-card { display: flex; flex-direction: column; gap: 6px; padding: 8px 10px; border: 1px solid #dbe3ef; border-radius: 8px; background: #fff; }
.note-top { display: flex; align-items: center; gap: 6px; }
.place-sel { width: 90px; }
.rm-btn { flex-shrink: 0; }
.note-text { width: 100%; resize: vertical; font-family: inherit; }
.ll-select { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.field-label { font-size: 11px; color: #64748b; flex-shrink: 0; }
.ll-chip {
  font-size: 11px; padding: 2px 8px; border-radius: 12px; cursor: pointer;
  border: 1px solid #cbd5e1; background: #f8fafc; color: #475569;
}
.ll-chip.selected { background: #eff6ff; border-color: #93c5fd; color: #1d4ed8; }
.anchor-row { display: flex; align-items: center; gap: 6px; }
.anchor-sel { flex: 1; }
.mini-btn { min-width: 24px; height: 24px; border: 1px solid #cbd5e1; background: #fff; border-radius: 5px; cursor: pointer; font-size: 14px; color: #374151; }
.mini-btn:disabled { opacity: .45; cursor: not-allowed; }
.inp {
  padding: 4px 6px; border: 1px solid #cbd5e1; border-radius: 5px;
  font-size: 12px; background: white; color: #1e293b; outline: none; box-sizing: border-box;
}
.inp:focus { border-color: #3b82f6; box-shadow: 0 0 0 2px #bfdbfe; }
</style>
