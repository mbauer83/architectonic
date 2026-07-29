<script setup lang="ts">
/**
 * Config-driven editor for a diagram-only entity's editable descriptive metadata. The field list,
 * order, and input widget all come from the diagram type's `editable_metadata` config (the single
 * source of truth) — nothing about WHICH fields exist or ARE editable is hardcoded here. A ✎ toggle
 * swaps the read-only rows into inputs in place; `save` emits the patch (only these fields, coerced
 * to wire shape). Structural fields live in the host panel, never here.
 */
import { computed, ref } from 'vue'
import type { EditableMetadataField } from '../../../domain'

const props = defineProps<{
  fields: readonly EditableMetadataField[]
  values: Record<string, unknown>
  title?: string
}>()
const emit = defineEmits<{ save: [patch: Record<string, unknown>] }>()

const asText = (v: unknown): string => {
  if (typeof v === 'string') return v
  return typeof v === 'number' || typeof v === 'boolean' ? String(v) : ''
}
const asTags = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [])
const asBool = (v: unknown): boolean => v === true

const label = (field: string): string => field.charAt(0).toUpperCase() + field.slice(1).replace(/_/g, ' ')
const displayValue = (f: EditableMetadataField): string => {
  const v = props.values[f.field]
  if (f.control === 'tags') return asTags(v).join(', ')
  if (f.control === 'boolean') return asBool(v) ? 'yes' : ''
  return asText(v)
}
const shownFields = computed(() => props.fields.filter((f) => displayValue(f) !== ''))
const hasAny = computed(() => shownFields.value.length > 0)

const editing = ref(false)
const draft = ref<Record<string, string | boolean>>({})
const startEdit = () => {
  const next: Record<string, string | boolean> = {}
  for (const f of props.fields) {
    const v = props.values[f.field]
    next[f.field] = f.control === 'boolean' ? asBool(v) : f.control === 'tags' ? asTags(v).join(', ') : asText(v)
  }
  draft.value = next
  editing.value = true
}
const setValue = (field: string, value: string | boolean) => { draft.value = { ...draft.value, [field]: value } }
const save = () => {
  const patch: Record<string, unknown> = {}
  for (const f of props.fields) {
    const raw = draft.value[f.field]
    patch[f.field] = f.control === 'tags'
      ? String(raw).split(',').map((t) => t.trim()).filter(Boolean)
      : raw
  }
  emit('save', patch)
  editing.value = false
}
</script>

<template>
  <div class="emeta">
    <div class="emeta-hdr">
      <span class="emeta-title">{{ title ?? 'Metadata' }}</span>
      <button
        v-if="!editing && fields.length"
        class="emeta-edit"
        title="Edit metadata"
        @click="startEdit"
      >
        ✎
      </button>
    </div>

    <dl
      v-if="!editing"
      class="emeta-fields"
    >
      <template
        v-for="f in shownFields"
        :key="f.field"
      >
        <dt>{{ label(f.field) }}</dt>
        <dd>{{ displayValue(f) }}</dd>
      </template>
      <dd
        v-if="!hasAny"
        class="emeta-empty"
      >
        No metadata yet — press ✎ to add.
      </dd>
    </dl>

    <div
      v-else
      class="emeta-fields"
    >
      <template
        v-for="f in fields"
        :key="f.field"
      >
        <dt>{{ label(f.field) }}</dt>
        <dd>
          <input
            v-if="f.control === 'boolean'"
            type="checkbox"
            :checked="draft[f.field] === true"
            @change="setValue(f.field, ($event.target as HTMLInputElement).checked)"
          >
          <textarea
            v-else-if="f.control === 'summary' || f.control === 'notes'"
            class="emeta-input"
            rows="2"
            :value="String(draft[f.field] ?? '')"
            :placeholder="f.control === 'summary' ? 'Short summary' : ''"
            @input="setValue(f.field, ($event.target as HTMLTextAreaElement).value)"
          />
          <input
            v-else
            class="emeta-input"
            :value="String(draft[f.field] ?? '')"
            :placeholder="f.control === 'tags' ? 'comma, separated' : ''"
            @input="setValue(f.field, ($event.target as HTMLInputElement).value)"
          >
        </dd>
      </template>
    </div>

    <div
      v-if="editing"
      class="emeta-actions"
    >
      <button
        class="emeta-cancel"
        @click="editing = false"
      >
        Cancel
      </button>
      <button
        class="emeta-save"
        @click="save"
      >
        Save
      </button>
    </div>
  </div>
</template>

<style scoped>
.emeta { margin-top: 4px; }
.emeta-hdr { display: flex; align-items: center; justify-content: space-between; }
.emeta-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; }
.emeta-edit { border: none; background: none; cursor: pointer; color: #9ca3af; font-size: 13px; }
.emeta-edit:hover { color: #374151; }
.emeta-fields {
  display: grid; grid-template-columns: auto 1fr; gap: 6px 10px;
  margin: 8px 0 0; font-size: 12px; align-items: start;
}
.emeta-fields dt { color: #6b7280; font-weight: 500; padding-top: 4px; }
.emeta-fields dd { margin: 0; color: #111827; word-break: break-word; }
.emeta-empty { grid-column: 1 / -1; color: #9ca3af; }
.emeta-input {
  width: 100%; padding: 4px 6px; border: 1px solid #d1d5db; border-radius: 4px;
  font: inherit; font-size: 12px; box-sizing: border-box; resize: vertical;
}
.emeta-input:focus { outline: none; border-color: #2563eb; }
.emeta-actions { display: flex; justify-content: flex-end; gap: 6px; margin-top: 8px; }
.emeta-actions button { padding: 5px 12px; border-radius: 5px; cursor: pointer; font-size: 12px; }
.emeta-cancel { border: 1px solid #d1d5db; background: white; color: #374151; }
.emeta-save { border: 0; background: #2563eb; color: white; }
</style>
