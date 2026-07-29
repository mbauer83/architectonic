<script setup lang="ts">
/**
 * Selected datatype attribute (field) detail. Structural facets — name, type, key membership —
 * are read-only (renaming/retyping/reordering/deletion belong to the edit-mode DatatypeEditor).
 * The editable descriptive metadata is rendered by the config-driven EditableMetadataFields: which
 * fields exist and are editable comes entirely from the diagram type's `editable_metadata` config,
 * never hardcoded here. `save` re-emits the patch addressed by classifier + attribute id.
 */
import { computed } from 'vue'
import type { EditableMetadataSpec } from '../../../domain'
import type { AttributeDetail } from './attributeSelection'
import EditableMetadataFields from './EditableMetadataFields.vue'

const props = defineProps<{
  detail: AttributeDetail
  editableMetadataByType?: Record<string, EditableMetadataSpec> | null
}>()
const emit = defineEmits<{
  close: []
  save: [payload: { classifierId: string; attributeId: string; patch: Record<string, unknown> }]
}>()

const fields = computed(() => props.editableMetadataByType?.[props.detail.ownerType]?.subparts?.attributes ?? [])
const values = computed<Record<string, unknown>>(() => props.detail as unknown as Record<string, unknown>)
const onSave = (patch: Record<string, unknown>) => {
  const attributeId = props.detail.attributeId
  if (!attributeId) return
  emit('save', { classifierId: props.detail.classifierId, attributeId, patch })
}
</script>

<template>
  <div class="ent-det">
    <div class="det-hdr">
      <span class="det-name">{{ detail.name }}</span>
      <button
        class="det-close"
        @click="$emit('close')"
      >
        ×
      </button>
    </div>
    <div class="det-chips">
      <span class="chip chip-type">attribute</span>
      <span
        v-for="badge in detail.badges"
        :key="badge"
        class="chip chip-key"
      >{{ badge }}</span>
    </div>

    <dl
      v-if="detail.typeLabel"
      class="attr-struct"
    >
      <dt>Type</dt><dd>{{ detail.typeLabel }}</dd>
    </dl>

    <EditableMetadataFields
      v-if="detail.attributeId && fields.length"
      :fields="fields"
      :values="values"
      @save="onSave"
    />

    <div class="attr-owner">
      on {{ detail.ownerLabel }}
    </div>
  </div>
</template>

<style scoped>
.ent-det { border-top: 1px solid #e5e7eb; padding: 12px; }
.det-hdr { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.det-name { font-weight: 600; font-size: 14px; color: #111827; }
.det-close { border: none; background: none; font-size: 18px; line-height: 1; cursor: pointer; color: #9ca3af; }
.det-close:hover { color: #374151; }
.det-chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.chip { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: #f3f4f6; color: #374151; }
.chip-type { background: #e0e7ff; color: #3730a3; }
.chip-key { background: #fef3c7; color: #92400e; }
.attr-struct { display: grid; grid-template-columns: auto 1fr; gap: 6px 10px; margin: 0 0 4px; font-size: 12px; }
.attr-struct dt { color: #6b7280; font-weight: 500; }
.attr-struct dd { margin: 0; color: #111827; word-break: break-word; }
.attr-owner { margin-top: 10px; font-size: 11px; color: #9ca3af; }
</style>
