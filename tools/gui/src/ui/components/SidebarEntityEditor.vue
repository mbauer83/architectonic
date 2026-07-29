<script setup lang="ts">
/**
 * Sidebar detail + light editor for a FILE-BACKED model entity selected in a diagram. Read-only
 * view shows the rendered content; a ✎ swaps in editable summary, status, and profile attributes
 * (the entity's typed properties) in place. Deliberately NOT editable here: name, specialization,
 * existence, and connections — those are structural and belong to the entity page / model tools.
 * The heavy lifting (schema fetch, typed rows, attribute-type preservation, and preserving the
 * untouched fields on save) is reused from `useEntityEditForm`; this only surfaces the allowed
 * subset. `saved` asks the parent to reload the diagram so the change is reflected.
 */
import { computed, inject, ref } from 'vue'
import { modelServiceKey } from '../keys'
import { useEntityEditForm } from '../composables/useEntityEditForm'
import type { EntityDetail } from '../../domain'
import TypedPropertyInput from './TypedPropertyInput.vue'

const props = defineProps<{ entity: EntityDetail; contentHtml: string | null }>()
const emit = defineEmits<{ saved: [] }>()
const svc = inject(modelServiceKey)!

const detail = computed<EntityDetail | null>(() => props.entity)
const entityId = computed(() => props.entity.artifact_id)
const edit = useEntityEditForm({
  svc,
  entityId,
  detail,
  editFn: ref(svc.editEntity),
  onSaved: () => emit('saved'),
})
</script>

<template>
  <div class="see">
    <template v-if="!edit.editing">
      <div
        v-if="contentHtml"
        class="det-content markdown-body"
        v-html="contentHtml"
      />
      <button
        class="see-edit"
        @click="edit.startEdit()"
      >
        ✎ Edit metadata
      </button>
    </template>

    <div
      v-else
      class="see-form"
    >
      <label class="see-field">
        <span class="see-lbl">Summary</span>
        <textarea
          v-model="edit.editSummary"
          class="see-input"
          rows="3"
        />
      </label>
      <label class="see-field">
        <span class="see-lbl">Status</span>
        <select
          v-model="edit.editStatus"
          class="see-input"
        >
          <option value="draft">draft</option>
          <option value="active">active</option>
          <option value="deprecated">deprecated</option>
        </select>
      </label>

      <div
        v-if="edit.editProperties.length"
        class="see-props"
      >
        <span class="see-lbl">Attributes</span>
        <div
          v-for="(row, i) in edit.editProperties"
          :key="i"
          class="see-prop"
        >
          <span
            class="see-prop-key"
            :title="row.key"
          >{{ row.key }}<b
            v-if="edit.editSchemaRequired.has(row.key)"
            class="see-req"
          > *</b></span>
          <TypedPropertyInput
            v-model="row.value"
            :descriptor="edit.editSchemaDescriptors[row.key] ?? { type: row.adHocType }"
            :required="edit.editSchemaRequired.has(row.key)"
          />
        </div>
      </div>

      <div
        v-if="edit.editError"
        class="see-err"
      >
        {{ edit.editError }}
      </div>
      <div class="see-actions">
        <button
          class="see-cancel"
          @click="edit.cancelEdit()"
        >
          Cancel
        </button>
        <button
          class="see-save"
          :disabled="edit.editBusy || edit.editRequiredMissing"
          @click="edit.saveEdit()"
        >
          Save
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.see { font-size: 12px; }
.det-content { line-height: 1.5; color: #374151; margin-bottom: 8px; max-height: 220px; overflow-y: auto; }
.det-content :deep(p) { margin: 0.35rem 0; }
.det-content :deep(h1), .det-content :deep(h2), .det-content :deep(h3) { margin-top: 0; }
.see-edit {
  border: 1px solid #c7d2fe; background: #eef2ff; color: #4338ca;
  border-radius: 6px; padding: 4px 10px; font-size: 12px; cursor: pointer;
}
.see-edit:hover { background: #e0e7ff; }
.see-form { display: grid; gap: 10px; }
.see-field { display: grid; gap: 4px; }
.see-lbl { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; }
.see-input {
  width: 100%; padding: 5px 7px; border: 1px solid #d1d5db; border-radius: 5px;
  font: inherit; font-size: 12px; box-sizing: border-box; resize: vertical;
}
.see-input:focus { outline: none; border-color: #2563eb; }
.see-props { display: grid; gap: 6px; }
.see-prop { display: grid; grid-template-columns: 110px 1fr; gap: 8px; align-items: center; }
.see-prop-key { font-size: 12px; color: #374151; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.see-req { color: #dc2626; }
.see-err { font-size: 12px; color: #dc2626; }
.see-actions { display: flex; justify-content: flex-end; gap: 6px; }
.see-actions button { padding: 5px 12px; border-radius: 5px; cursor: pointer; font-size: 12px; }
.see-cancel { border: 1px solid #d1d5db; background: white; color: #374151; }
.see-save { border: 0; background: #2563eb; color: white; }
.see-save:disabled { opacity: .5; cursor: not-allowed; }
</style>
