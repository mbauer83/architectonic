<script setup lang="ts">
/**
 * The entity-detail edit form's card body: summary/keywords/specialization/notes,
 * ad-hoc-vs-schema-typed property rows, dry-run preview, and the cancel/preview/save action
 * row (mirroring the header's own trio — same injected `edit` bundle, same handlers, so
 * both act on one transaction). Injected, not a prop — its fields are v-model-bound here,
 * and a prop can't legitimately be mutated (`vue/no-mutating-props`).
 */
import { inject } from 'vue'
import { specializationOptionLabel } from '../lib/specializationOptions'
import { entityEditFormKey } from '../composables/useEntityEditForm'
import TypedPropertyInput from './TypedPropertyInput.vue'
import SchemaQuarantineBanner from './SchemaQuarantineBanner.vue'
import { editBlockedReason } from '../lib/entityEditBlocking'

const emit = defineEmits<{ 'open-reference-picker': [field: 'summary' | 'notes'] }>()
const edit = inject(entityEditFormKey)!
</script>

<template>
  <div class="edit-form card">
    <div class="form-row">
      <label class="form-label">Summary</label>
      <div class="field-tools">
        <button
          class="insert-ref-btn"
          type="button"
          @click="emit('open-reference-picker', 'summary')"
        >
          Insert Reference
        </button>
      </div>
      <textarea
        :ref="(el) => { edit.summaryTextareaRef = el as HTMLTextAreaElement | null }"
        v-model="edit.editSummary"
        class="edit-textarea"
        rows="3"
      />
    </div>
    <div class="form-row">
      <label class="form-label">Keywords <span class="form-hint">(comma-separated)</span></label>
      <input
        v-model="edit.editKeywords"
        class="edit-input"
        placeholder="e.g. model, tooling, automation"
      >
    </div>
    <div
      v-if="edit.editSpecializationOptions.length"
      class="form-row"
    >
      <label class="form-label">
        Specializations <span class="form-hint">(optional; ⌘/Ctrl-click for several)</span>
      </label>
      <select
        v-model="edit.editSpecializations"
        class="edit-select"
        multiple
        size="4"
      >
        <option
          v-for="spec in edit.editSpecializationOptions"
          :key="spec.slug"
          :value="spec.slug"
        >
          {{ specializationOptionLabel(spec) }}
        </option>
      </select>
    </div>
    <div class="form-row">
      <label class="form-label">Notes</label>
      <div class="field-tools">
        <button
          class="insert-ref-btn"
          type="button"
          @click="emit('open-reference-picker', 'notes')"
        >
          Insert Reference
        </button>
      </div>
      <textarea
        :ref="(el) => { edit.notesTextareaRef = el as HTMLTextAreaElement | null }"
        v-model="edit.editNotes"
        class="edit-textarea"
        rows="3"
      />
    </div>
    <div class="form-row">
      <label class="form-label">Properties</label>
      <div
        v-for="(row, i) in edit.editProperties"
        :key="i"
        class="prop-row"
      >
        <span
          v-if="edit.editSchemaDescriptors[row.key]"
          class="prop-key-label"
          :title="row.key"
        >{{ row.key }}<span
          v-if="edit.editSchemaRequired.has(row.key)"
          class="prop-required"
        > *</span></span>
        <input
          v-else
          v-model="row.key"
          class="prop-key"
          placeholder="key"
        >
        <TypedPropertyInput
          v-if="edit.editSchemaDescriptors[row.key]"
          v-model="row.value"
          :descriptor="edit.editSchemaDescriptors[row.key]"
          :required="edit.editSchemaRequired.has(row.key)"
        />
        <template v-else>
          <select
            v-model="row.adHocType"
            class="prop-type-select"
            title="Value type"
            @change="row.value = row.adHocType === 'boolean' ? 'false' : ''"
          >
            <option value="string">
              text
            </option>
            <option value="integer">
              integer
            </option>
            <option value="number">
              number
            </option>
            <option value="boolean">
              boolean
            </option>
            <option value="array">
              array
            </option>
          </select>
          <TypedPropertyInput
            v-model="row.value"
            :descriptor="{ type: row.adHocType }"
          />
        </template>
        <button
          class="icon-btn remove-prop-btn"
          :disabled="edit.editSchemaRequired.has(row.key)"
          @click="edit.removePropertyRow(i)"
        >
          ×
        </button>
      </div>
      <button
        class="add-prop-btn"
        @click="edit.addPropertyRow()"
      >
        + Add property
      </button>
    </div>

    <div
      v-if="edit.editPreview"
      class="preview-box"
    >
      <div class="preview-header">
        Dry-run preview
      </div>
      <div
        v-if="edit.editPreview.warnings.length"
        class="preview-warnings"
      >
        <div
          v-for="w in edit.editPreview.warnings"
          :key="w"
          class="preview-warn"
        >
          {{ w }}
        </div>
      </div>
      <pre
        v-if="edit.editPreview.content"
        class="preview-content"
      >{{ edit.editPreview.content }}</pre>
    </div>

    <SchemaQuarantineBanner
      :quarantine="edit.editQuarantine"
      :artifact-type="edit.editArtifactType"
      :specialization="edit.editSpecializations.join(', ')"
    />

    <div
      v-if="edit.editError"
      class="state-msg state-msg--error"
    >
      {{ edit.editError }}
    </div>

    <div class="edit-actions">
      <button
        class="cancel-btn"
        :disabled="edit.editBusy"
        @click="edit.cancelEdit()"
      >
        Cancel
      </button>
      <button
        class="preview-btn"
        :disabled="edit.editBusy || edit.editQuarantine.quarantined"
        :title="editBlockedReason(edit.editQuarantine.quarantined, false)"
        @click="edit.previewEdit()"
      >
        Preview
      </button>
      <button
        class="save-btn"
        :disabled="edit.editBusy || edit.editRequiredMissing || edit.editQuarantine.quarantined"
        :title="editBlockedReason(edit.editQuarantine.quarantined, edit.editRequiredMissing)"
        @click="edit.saveEdit()"
      >
        Save
      </button>
    </div>
  </div>
</template>

<style scoped>
.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; }
.state-msg { color: #6b7280; padding: 4px 0; }
.state-msg--error { color: #dc2626; }

.edit-form { padding: 20px; margin-bottom: 24px; }
.form-row { margin-bottom: 14px; }
.form-label { display: block; font-size: 12px; font-weight: 600; color: #374151; margin-bottom: 4px; text-transform: uppercase; letter-spacing: .04em; }
.form-hint { font-weight: 400; text-transform: none; color: #9ca3af; }
.field-tools { display: flex; justify-content: flex-end; margin-bottom: 6px; }
.insert-ref-btn {
  padding: 4px 10px; border-radius: 6px; border: 1px solid #d1d5db;
  background: #f8fafc; color: #374151; font-size: 12px; cursor: pointer;
}
.insert-ref-btn:hover { background: #f1f5f9; }
.edit-input {
  width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid #d1d5db;
  font-size: 13px; outline: none; box-sizing: border-box;
}
.edit-input:focus { border-color: #2563eb; }
.edit-select {
  width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid #d1d5db;
  font-size: 13px; outline: none; box-sizing: border-box; background: white;
}
.edit-select:focus { border-color: #2563eb; }
.edit-textarea {
  width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid #d1d5db;
  font-size: 13px; outline: none; resize: vertical; box-sizing: border-box; font-family: inherit;
}
.edit-textarea:focus { border-color: #2563eb; }

.prop-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: flex-start; }
.prop-key-label {
  flex: 0 0 150px; font-size: 12px; font-weight: 500; color: #374151;
  padding-top: 7px; overflow-wrap: break-word; min-width: 0;
}
.prop-required { color: #dc2626; }
.prop-key {
  flex: 0 0 150px; padding: 6px 8px; border-radius: 6px; border: 1px solid #d1d5db;
  font-size: 12px; outline: none; box-sizing: border-box; min-width: 0;
}
.prop-key:focus { border-color: #2563eb; }
.prop-type-select {
  flex: 0 0 auto; padding: 6px; border-radius: 6px; border: 1px solid #d1d5db;
  font-size: 12px; color: #374151; background: white; outline: none; cursor: pointer;
}
.prop-type-select:focus { border-color: #2563eb; }
.prop-row .remove-prop-btn { margin-top: 5px; }
.add-prop-btn {
  font-size: 12px; color: #2563eb; background: none; border: none; cursor: pointer; padding: 4px 0;
}
.add-prop-btn:hover { text-decoration: underline; }
.remove-prop-btn {
  width: 22px; height: 22px; border-radius: 4px; border: 1px solid #fecaca;
  background: white; cursor: pointer; color: #dc2626; font-size: 14px;
  display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.remove-prop-btn:hover { background: #fef2f2; }

.preview-box { background: #f9fafb; border-radius: 6px; padding: 12px; margin-bottom: 12px; }
.preview-header { font-size: 11px; font-weight: 600; text-transform: uppercase; color: #6b7280; margin-bottom: 8px; }
.preview-warnings { margin-bottom: 8px; }
.preview-warn { font-size: 12px; color: #b45309; }
.preview-content { font-size: 11px; color: #374151; white-space: pre-wrap; max-height: 200px; overflow-y: auto; font-family: monospace; }

.edit-actions { display: flex; gap: 8px; justify-content: flex-end; padding-top: 4px; }
.cancel-btn {
  padding: 7px 16px; background: #f3f4f6; color: #374151; border: 1px solid #d1d5db;
  border-radius: 6px; font-size: 13px; cursor: pointer;
}
.cancel-btn:hover:not(:disabled) { background: #e5e7eb; }
.preview-btn {
  padding: 7px 16px; background: #f3f4f6; color: #1d4ed8; border: 1px solid #bfdbfe;
  border-radius: 6px; font-size: 13px; cursor: pointer; font-weight: 500;
}
.preview-btn:hover:not(:disabled) { background: #eff6ff; }
.save-btn {
  padding: 7px 16px; background: #2563eb; color: white; border: none;
  border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer;
}
.save-btn:hover:not(:disabled) { background: #1d4ed8; }
.cancel-btn:disabled, .preview-btn:disabled, .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
