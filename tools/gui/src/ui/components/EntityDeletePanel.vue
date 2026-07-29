<script setup lang="ts">
/**
 * Delete-confirmation panel for an entity: dry-run preview before a real delete. Fully
 * self-contained — injects the model service and owns its own confirm/preview/mutation
 * state; the parent calls the exposed `requestDelete()` from its own "Delete" button and
 * listens for `deleted` to navigate away.
 */
import { computed, inject, ref } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { readErrorMessage } from '../lib/errors'
import type { WriteResult } from '../../domain'

const props = defineProps<{
  entityId: string
  isGlobalEntity: boolean
  adminMode: boolean
}>()
const emit = defineEmits<{ deleted: [] }>()

const svc = inject(modelServiceKey)!
const deleteFn = computed(() => (props.isGlobalEntity && props.adminMode) ? svc.adminDeleteEntity : svc.deleteEntity)

const confirmDelete = ref(false)
const deleteBusy = ref(false)
const deleteError = ref<string | null>(null)
const deletePreview = ref<{ content: string | null; warnings: string[] } | null>(null)

const requestDelete = () => {
  confirmDelete.value = true
  deleteBusy.value = true
  deleteError.value = null
  deletePreview.value = null
  void Effect.runPromise(deleteFn.value({ artifact_id: props.entityId, dry_run: true })).then((r: WriteResult) => {
    deleteBusy.value = false
    deletePreview.value = { content: r.content, warnings: [...r.warnings] }
  }).catch((reason: unknown) => {
    deleteBusy.value = false
    deleteError.value = readErrorMessage(reason)
  })
}
defineExpose({ requestDelete })

const cancel = () => {
  confirmDelete.value = false
  deletePreview.value = null
  deleteError.value = null
}

const executeDelete = () => {
  deleteBusy.value = true
  deleteError.value = null
  void Effect.runPromise(deleteFn.value({ artifact_id: props.entityId, dry_run: false })).then((r: WriteResult) => {
    deleteBusy.value = false
    if (r.wrote) {
      emit('deleted')
    } else {
      deleteError.value = r.content ?? 'Delete failed'
    }
  }).catch((reason: unknown) => {
    deleteBusy.value = false
    deleteError.value = readErrorMessage(reason)
  })
}
</script>

<template>
  <div
    v-if="confirmDelete"
    class="delete-panel card"
  >
    <div class="delete-title">
      Delete Entity
    </div>
    <div class="delete-text">
      Deletion removes the entity artifact and its owned outgoing file. It is blocked while
      other connections, diagrams, or global references still depend on the entity.
    </div>
    <div
      v-if="deletePreview?.warnings.length"
      class="preview-warnings"
    >
      <div
        v-for="w in deletePreview.warnings"
        :key="w"
        class="preview-warn"
      >
        {{ w }}
      </div>
    </div>
    <pre
      v-if="deletePreview?.content"
      class="delete-preview"
    >{{ deletePreview.content }}</pre>
    <pre
      v-if="deleteError"
      class="state-msg state-msg--error state-msg--block"
    >{{ deleteError }}</pre>
    <div class="edit-actions">
      <button
        class="cancel-btn"
        :disabled="deleteBusy"
        @click="cancel"
      >
        Cancel
      </button>
      <button
        class="delete-confirm-btn"
        :disabled="deleteBusy"
        @click="executeDelete"
      >
        {{ deleteBusy ? 'Deleting…' : 'Delete Entity' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; }
.state-msg { color: #6b7280; padding: 4px 0; }
.state-msg--error { color: #dc2626; }
.state-msg--block { white-space: pre-wrap; overflow-x: auto; }
.delete-panel { padding: 16px; margin-bottom: 24px; border-color: #fecaca; background: #fff7f7; }
.delete-title { font-size: 14px; font-weight: 700; color: #991b1b; margin-bottom: 6px; }
.delete-text { font-size: 13px; color: #7f1d1d; margin-bottom: 10px; }
.preview-warnings { margin-bottom: 8px; }
.preview-warn { font-size: 12px; color: #b45309; }
.delete-preview {
  font-size: 11px; color: #374151; white-space: pre-wrap; max-height: 260px; overflow-y: auto;
  font-family: monospace; background: #fff; border: 1px solid #fecaca; border-radius: 6px; padding: 10px;
}
.edit-actions { display: flex; gap: 8px; justify-content: flex-end; padding-top: 4px; }
.cancel-btn {
  padding: 7px 16px; background: #f3f4f6; color: #374151; border: 1px solid #d1d5db;
  border-radius: 6px; font-size: 13px; cursor: pointer;
}
.cancel-btn:hover:not(:disabled) { background: #e5e7eb; }
.delete-confirm-btn {
  padding: 7px 16px; background: #dc2626; color: white; border: none;
  border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer;
}
.delete-confirm-btn:hover:not(:disabled) { background: #b91c1c; }
.cancel-btn:disabled, .delete-confirm-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
