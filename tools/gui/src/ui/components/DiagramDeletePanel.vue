<script setup lang="ts">
/**
 * Delete-confirmation panel for a diagram: dry-run preview (content + warnings) before a
 * real delete. Fully self-contained — injects the model service and owns its own
 * confirm/preview/mutation state; the parent only calls `requestDelete()` (exposed, via a
 * template ref) from its own "Delete" button, and listens for `deleted` to navigate away.
 */
import { computed, inject, ref } from 'vue'
import { Exit } from 'effect'
import { modelServiceKey } from '../keys'
import { useMutation } from '../composables/useMutation'
import type { RepoError } from '../../ports/ModelRepository'
import type { WriteResult } from '../../domain'

const props = defineProps<{
  diagramId: string
  isGlobalDiagram: boolean
  adminMode: boolean
}>()
const emit = defineEmits<{ deleted: [] }>()

const svc = inject(modelServiceKey)!
const deleteMutation = useMutation<WriteResult, RepoError>()
const confirmDelete = ref(false)
const deletePreview = ref<{ content: string | null; warnings: string[] } | null>(null)

const deleteFn = computed(() =>
  (props.isGlobalDiagram && props.adminMode) ? svc.adminDeleteDiagram : svc.deleteDiagram,
)
const deleteError = computed(() => {
  const r = deleteMutation.result.value
  if (r && !r.wrote) return r.content ?? 'Delete failed'
  return deleteMutation.errorMessage.value
})

const requestDelete = () => {
  confirmDelete.value = true
  deletePreview.value = null
  deleteMutation.reset()
  void deleteMutation.run(deleteFn.value({ artifact_id: props.diagramId, dry_run: true }))
    .then((exit) => Exit.match(exit, {
      onSuccess: (r) => { deletePreview.value = { content: r.content, warnings: [...r.warnings] } },
      onFailure: () => {},
    }))
}
defineExpose({ requestDelete })

const cancel = () => {
  confirmDelete.value = false
  deletePreview.value = null
  deleteMutation.reset()
}

const executeDelete = () => {
  void deleteMutation.run(deleteFn.value({ artifact_id: props.diagramId, dry_run: false }))
    .then((exit) => Exit.match(exit, {
      onSuccess: (r) => { if (r.wrote) emit('deleted') },
      onFailure: () => {},
    }))
}
</script>

<template>
  <div
    v-if="confirmDelete"
    class="delete-panel"
  >
    <div class="delete-title">
      Delete Diagram
    </div>
    <div class="delete-text">
      Deletion removes the diagram source file and any rendered PNG/SVG siblings.
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
      class="state err state-block"
    >{{ deleteError }}</pre>
    <div class="delete-actions">
      <button
        class="toggle-btn"
        :disabled="deleteMutation.running.value"
        @click="cancel"
      >
        Cancel
      </button>
      <button
        class="delete-confirm-btn"
        :disabled="deleteMutation.running.value"
        @click="executeDelete"
      >
        {{ deleteMutation.running.value ? 'Deleting…' : 'Delete Diagram' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.state { color: #6b7280; } .err { color: #dc2626; }
.state-block { white-space: pre-wrap; overflow-x: auto; }
.delete-panel { margin-top: 16px; padding: 16px; background: #fff7f7; border: 1px solid #fecaca; border-radius: 8px; }
.delete-title { font-size: 14px; font-weight: 700; color: #991b1b; margin-bottom: 6px; }
.delete-text { font-size: 13px; color: #7f1d1d; margin-bottom: 10px; }
.preview-warnings { display: flex; flex-direction: column; gap: 2px; margin-bottom: 10px; }
.preview-warn { font-size: 12px; color: #92400e; background: #fef3c7; padding: 4px 8px; border-radius: 4px; }
.delete-preview {
  font-size: 11px; color: #374151; white-space: pre-wrap; max-height: 260px; overflow-y: auto;
  font-family: monospace; background: white; border: 1px solid #fecaca; border-radius: 6px; padding: 10px; margin-bottom: 10px;
}
.delete-actions { display: flex; gap: 8px; justify-content: flex-end; }
.toggle-btn { padding: 5px 14px; border-radius: 6px; border: 1px solid #d1d5db; background: white; font-size: 13px; cursor: pointer; color: #374151; } .toggle-btn:hover { background: #f9fafb; }
.delete-confirm-btn {
  padding: 5px 16px; background: #dc2626; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; color: white; cursor: pointer;
}
.delete-confirm-btn:hover:not(:disabled) { background: #b91c1c; }
.delete-confirm-btn:disabled { opacity: .5; cursor: not-allowed; }
</style>
