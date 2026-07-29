<script setup lang="ts">
import type { EntityDisplayInfo } from '../../domain'
import EntityPickerInput from './EntityPickerInput.vue'

defineProps<{ placeholder?: string; artifactType?: string }>()
const emit = defineEmits<{ select: [id: string, name: string] }>()

const selectEntity = (entity: EntityDisplayInfo) => {
  emit('select', entity.artifact_id, entity.name)
}
</script>

<template>
  <EntityPickerInput
    :placeholder="placeholder ?? 'Search entities by name or ID...'"
    :fixed-entity-types="artifactType ? [artifactType] : undefined"
    widenable-to="none"
    close-on-select
    @select="selectEntity"
  />
</template>
