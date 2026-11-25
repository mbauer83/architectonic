<script setup lang="ts">
/**
 * A box's menu on the canvas (D9, A-02.39): *Rename box…*, *Box by type ▸* — a box of one element type
 * inside this one — and *Delete box*, which takes the box off the diagram and never what it holds. A
 * layer or type box the renderer computed is written down, with its siblings, the first time one is
 * edited (`useCanvasBoxes`). Each entry is one undoable step.
 */
import { computed, ref } from 'vue'
import type { DiagramEditing } from '../composables/useDiagramEditing'
import { useCanvasBoxes } from '../composables/useCanvasBoxes'
import CanvasMenu from './CanvasMenu.vue'
import CanvasLabelForm from './CanvasLabelForm.vue'
import type { CanvasMenuItem } from './canvasMenu'
import { typeWords } from './canvasTypeList'

const props = defineProps<{
  editing: DiagramEditing
  box: { readonly alias: string; readonly label: string }
  /** The elements on the diagram, with their types: what a type box may be made of. */
  members: readonly { readonly alias: string; readonly type: string }[]
}>()
const emit = defineEmits<{ done: []; close: [] }>()
const boxes = useCanvasBoxes(props.editing)

const page = ref<'top' | 'types' | 'rename'>('top')
/** How a type box is labelled: the type's words, each capitalised, as a layer box names its layer. */
const labelOf = (type: string) => typeWords(type).replace(/\b\w/g, (letter) => letter.toUpperCase())

/** The types of the elements this box holds itself — not in a box inside it — each once. */
const types = computed(() => {
  const inside = new Set((props.editing.session.geometry.value?.elements ?? [])
    .filter((one) => one.inside === props.box.alias).map((one) => one.alias))
  return [...new Set(props.members.filter((one) => inside.has(one.alias) && one.type).map((one) => one.type))]
})

const items = computed((): readonly CanvasMenuItem[] => (page.value === 'types'
  ? [...types.value.map((type) => ({
    id: `type:${type}`, label: labelOf(type), hint: `every ${typeWords(type)} in it`, command: 'box.by-type' as const,
  })),
    { id: 'back', label: '‹ Back', divider: true }]
  : [
    { id: 'rename', label: 'Rename box…', hint: 'on this diagram only', command: 'box.rename' },
    ...types.value.length ? [{ id: 'types', label: 'Box by type ▸', hint: 'a box of one element type inside it', command: 'box.by-type' as const }]
      : [],
    {
      id: 'delete', label: 'Delete box', hint: 'what it holds stays on the diagram', danger: true, divider: true,
      command: 'box.delete',
    },
  ]))

const settle = async (step: Promise<boolean>) => {
  if (await step) emit('done')
  else emit('close')
}
const choose = (id: string) => {
  if (id === 'back') page.value = 'top'
  else if (id === 'types' || id === 'rename') page.value = id
  else if (id === 'delete') void settle(boxes.remove(props.box.alias))
  else if (id.startsWith('type:')) {
    const type = id.slice('type:'.length)
    void settle(boxes.addTypeBox(props.box.alias, type, labelOf(type)))
  }
}
</script>

<template>
  <CanvasLabelForm
    v-if="page === 'rename'"
    :title="`Rename ${box.label}`"
    :value="box.label"
    field="Label"
    note="The box is renamed on this diagram only; the model has no boxes."
    @keep="(label) => settle(boxes.rename(box.alias, label))"
    @cancel="emit('close')"
  />
  <CanvasMenu
    v-else
    :heading="page === 'types' ? `Box by type in ${box.label}` : box.label"
    :label="`${box.label}: box`"
    :items="items"
    @choose="choose"
    @close="emit('close')"
  />
</template>
