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
import CanvasMenu from './CanvasMenu.vue'
import type { CanvasMenuItem } from './canvasMenu'
import { STACKING_ITEMS, restackOf } from './canvasElementMenu'

const props = defineProps<{ editing: DiagramEditing; selection: readonly string[]; words: CanvasWords }>()
const emit = defineEmits<{ done: []; close: [] }>()

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

const heading = computed(() => page.value === 'top' ? `${props.selection.length} selected`
  : `${page.value === 'align' ? 'Align' : 'Distribute'} ${elements.value} elements`)
const items = computed((): readonly CanvasMenuItem[] => {
  if (page.value === 'align') {
    return [...EDGES.map(([edge, name]) => ({ id: edge, label: name })), { id: 'back', label: '‹ Back', divider: true }]
  }
  if (page.value === 'distribute') {
    return [...AXES.map(([axis, name]) => ({ id: axis, label: name, hint: 'equal gaps, the outer two stay' })),
      { id: 'back', label: '‹ Back', divider: true }]
  }
  return [
    { id: 'align', label: 'Align ▸', hint: 'left · centres · right · top · middles · bottoms',
      disabled: elements.value < LEAST_TO_ALIGN },
    ...elements.value >= LEAST_TO_DISTRIBUTE
      ? [{ id: 'distribute', label: 'Distribute ▸', hint: 'horizontally · vertically' }] : [],
    ...STACKING_ITEMS,
    ...props.words.removeEntry
      ? [{ id: 'remove', label: props.words.removeEntry, hint: props.words.removeHint, shortcut: props.words.removeKey,
        divider: true }]
      : [],
  ]
})
const choose = (id: string) => {
  const how = restackOf(id)
  if (how) {
    props.editing.restack(props.selection, how)
    emit('done')
  } else if (id === 'back') page.value = 'top'
  else if (id === 'align' || id === 'distribute') page.value = id
  else if (id === 'remove') remove()
  else if (page.value === 'align') align(id as AlignEdge)
  else distribute(id as DistributeAxis)
}
</script>

<template>
  <CanvasMenu
    :heading="heading"
    :label="page === 'top' ? 'Selection' : page === 'align' ? 'Align' : 'Distribute'"
    :items="items"
    @choose="choose"
    @close="emit('close')"
  />
</template>
