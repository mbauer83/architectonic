<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDisplayInfo } from '../../domain'
import {
  addOccurrence,
  occurrenceCount,
  occurrenceItems,
  removeOccurrence,
} from '../lib/archimateOccurrences'

const props = defineProps<{
  diagramEntities: Record<string, unknown>
  entities: EntityDisplayInfo[]
}>()

const emit = defineEmits<{
  change: [diagramEntities: Record<string, unknown>]
}>()

const entitiesById = computed(() => new Map(props.entities.map((entity) => [entity.artifact_id, entity])))
const occurrences = computed(() => occurrenceItems(props.diagramEntities))

const addFor = (entity: EntityDisplayInfo) => {
  emit('change', addOccurrence(props.diagramEntities, entity))
}

const remove = (id: string) => {
  emit('change', removeOccurrence(props.diagramEntities, id))
}
</script>

<template>
  <div
    v-if="entities.length"
    class="occ-panel"
  >
    <div class="occ-hdr">
      Occurrences
    </div>
    <div class="occ-rows">
      <div
        v-for="entity in entities"
        :key="entity.artifact_id"
        class="occ-row"
      >
        <span class="occ-name">{{ entity.name }}</span>
        <span
          v-if="occurrenceCount(diagramEntities, entity.artifact_id)"
          class="occ-count"
        >+{{ occurrenceCount(diagramEntities, entity.artifact_id) }}</span>
        <button
          class="occ-add"
          type="button"
          title="Add another visual occurrence"
          @click="addFor(entity)"
        >
          +
        </button>
      </div>
    </div>
    <div
      v-if="occurrences.length"
      class="occ-list"
    >
      <div
        v-for="occ in occurrences"
        :key="occ.id"
        class="occ-item"
      >
        <span class="occ-id">{{ entitiesById.get(occ.backing_entity_id)?.name ?? occ.backing_entity_id }}</span>
        <button
          class="occ-remove"
          type="button"
          title="Remove occurrence"
          @click="remove(occ.id)"
        >
          ×
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.occ-panel { border: 1px solid #e5e7eb; border-radius: 6px; background: #f9fafb; padding: 8px; }
.occ-hdr { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: #6b7280; margin-bottom: 6px; }
.occ-rows, .occ-list { display: flex; flex-direction: column; gap: 4px; }
.occ-list { margin-top: 8px; padding-top: 8px; border-top: 1px solid #e5e7eb; }
.occ-row, .occ-item { display: flex; align-items: center; gap: 6px; min-height: 24px; }
.occ-name, .occ-id { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: #374151; }
.occ-count { font-size: 10px; color: #1d4ed8; background: #dbeafe; border-radius: 999px; padding: 1px 6px; }
.occ-add, .occ-remove { width: 22px; height: 22px; border-radius: 4px; border: 1px solid #d1d5db; background: white; color: #374151; cursor: pointer; line-height: 1; }
.occ-add:hover, .occ-remove:hover { border-color: #93c5fd; color: #1d4ed8; }
</style>
