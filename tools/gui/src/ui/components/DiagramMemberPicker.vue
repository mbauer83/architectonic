<script setup lang="ts">
import { computed } from 'vue'
import EntityPickerInput from './EntityPickerInput.vue'
import type { DiagramContext } from '../../domain'

const props = defineProps<{ context: DiagramContext; busy: boolean }>()
const emit = defineEmits<{ add: [id: string, name: string, type?: string] }>()
const choices = computed(() => props.context.suggested_entities.filter(group => group.hop === 1).flatMap(g => g.items))
const excludedIds = computed(() => new Set(props.context.entities.map(e => e.artifact_id)))
</script>

<template>
  <section
    class="card member-picker"
    aria-label="Add from model"
  >
    <EntityPickerInput
      placeholder="Search model elements"
      :diagram-type="context.diagram.diagram_type"
      :excluded-ids="excludedIds"
      close-on-select
      @select="entity => emit('add', entity.artifact_id, entity.name, entity.artifact_type)"
    />
    <p>Drag onto the diagram to add it, or focus a row and press Enter.</p>
    <button
      v-for="item in choices"
      :key="item.artifact_id"
      type="button"
      draggable="true"
      :disabled="busy"
      @dragstart="$event.dataTransfer?.setData('application/x-architectonic-entity', item.artifact_id)"
      @click="emit('add', item.artifact_id, item.name)"
    >
      ⠿ {{ item.name }}
    </button>
  </section>
</template>

<style scoped>
.member-picker { display: grid; gap: .4rem; max-height: 20rem; overflow: auto; padding: .75rem; }
input { width: 100%; }
button { text-align: start; cursor: grab; }
p { margin: 0; font-size: .85em; }
</style>
