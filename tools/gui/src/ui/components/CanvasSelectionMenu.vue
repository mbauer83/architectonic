<script setup lang="ts">
/**
 * A multi-selection's menu (Q14): *Align ▸* — left edges, centres, right edges, top edges, middles,
 * bottom edges — and *Distribute ▸* — horizontally, vertically — then removing the selection. Align
 * needs two elements and Distribute three, the outer two staying; boxes move with their members, so
 * only elements are counted. Each command is one undoable step.
 */
import { computed, ref } from 'vue'
import type { AlignEdge, DistributeAxis } from '../../domain/layout/layoutIntents'
import { LEAST_TO_ALIGN, LEAST_TO_DISTRIBUTE } from '../../domain/layout/layoutIntents'
import { alignedSelection, distributedSelection, elementsOf } from '../../domain/layout/lab/labSelection'
import type { DiagramEditing } from '../composables/useDiagramEditing'
import type { CanvasWords } from './canvasWords'

const props = defineProps<{ editing: DiagramEditing; selection: readonly string[]; words: CanvasWords }>()
const emit = defineEmits<{ done: [] }>()

const EDGES: readonly (readonly [AlignEdge, string])[] = [
  ['left', 'Left edges'], ['centre_x', 'Centres'], ['right', 'Right edges'],
  ['top', 'Top edges'], ['centre_y', 'Middles'], ['bottom', 'Bottom edges'],
]
const AXES: readonly (readonly [DistributeAxis, string])[] = [['x', 'Horizontally'], ['y', 'Vertically']]

const page = ref<'top' | 'align' | 'distribute'>('top')
const elements = computed(() => {
  const where = props.editing.session.placement.value
  return where ? elementsOf(props.selection, where).size : 0
})

const align = (edge: AlignEdge) => {
  props.editing.session.change((geometry, now, where) => alignedSelection(geometry, now, where, props.selection, edge))
  emit('done')
}
const distribute = (axis: DistributeAxis) => {
  props.editing.session.change((geometry, now, where) =>
    distributedSelection(geometry, now, where, props.selection, axis))
  emit('done')
}
const remove = () => {
  props.editing.remove(props.selection)
  emit('done')
}
</script>

<template>
  <div
    class="selection-menu"
    role="menu"
    :aria-label="page === 'top' ? 'Selection' : page === 'align' ? 'Align' : 'Distribute'"
  >
    <template v-if="page === 'top'">
      <strong>{{ selection.length }} selected</strong>
      <button
        role="menuitem"
        :disabled="elements < LEAST_TO_ALIGN"
        title="left · centres · right · top · middles · bottoms"
        @click="page = 'align'"
      >
        Align ▸
      </button>
      <button
        v-if="elements >= LEAST_TO_DISTRIBUTE"
        role="menuitem"
        title="horizontally · vertically"
        @click="page = 'distribute'"
      >
        Distribute ▸
      </button>
      <button
        v-if="words.removeEntry"
        role="menuitem"
        @click="remove"
      >
        {{ words.removeEntry }}
      </button>
    </template>
    <template v-else>
      <strong>{{ page === 'align' ? 'Align' : 'Distribute' }} {{ elements }} elements</strong>
      <template v-if="page === 'align'">
        <button
          v-for="[edge, name] in EDGES"
          :key="edge"
          role="menuitem"
          @click="align(edge)"
        >
          {{ name }}
        </button>
      </template>
      <template v-else>
        <button
          v-for="[axis, name] in AXES"
          :key="axis"
          role="menuitem"
          title="equal gaps, the outer two stay"
          @click="distribute(axis)"
        >
          {{ name }}
        </button>
      </template>
      <button
        role="menuitem"
        @click="page = 'top'"
      >
        ‹ Back
      </button>
    </template>
  </div>
</template>

<style scoped>
.selection-menu button,
.selection-menu strong { display: block; margin-block: 0.25rem; }
</style>
