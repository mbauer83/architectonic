<script setup lang="ts">
/**
 * Datatype-classifier editable metadata, rendered inside the generic diagram sidebar via the
 * viewer extension's `entityDetailSection` hook (so the generic sidebar stays diagram-type
 * agnostic). Which fields exist and are editable comes entirely from the diagram type's
 * `editable_metadata` config; this is a thin wrapper that supplies the classifier's own record as
 * the value source and re-emits the patch keyed by classifier id. Values are read from the raw
 * diagram-entities record (authoritative — has list fields like `tags`), falling back to the
 * synthesized `entity.extra` for scalars.
 */
import { computed } from 'vue'
import type { EditableMetadataSpec, EntityDetail } from '../../../domain'
import EditableMetadataFields from './EditableMetadataFields.vue'

const props = defineProps<{
  entity: EntityDetail
  entityId: string
  record?: Record<string, unknown> | null
  editableMetadataByType?: Record<string, EditableMetadataSpec> | null
}>()
const emit = defineEmits<{
  save: [payload: { classifierId: string; patch: Record<string, unknown> }]
}>()

const values = computed<Record<string, unknown>>(() => props.record ?? props.entity.extra ?? {})
const fields = computed(() => props.editableMetadataByType?.[props.entity.artifact_type]?.entity ?? [])
const onSave = (patch: Record<string, unknown>) => emit('save', { classifierId: props.entityId, patch })
</script>

<template>
  <EditableMetadataFields
    v-if="fields.length"
    class="clf-meta"
    :fields="fields"
    :values="values"
    @save="onSave"
  />
</template>

<style scoped>
.clf-meta { padding-top: 8px; border-top: 1px dashed #e5e7eb; }
</style>
