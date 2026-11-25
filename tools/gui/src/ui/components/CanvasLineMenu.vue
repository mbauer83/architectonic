<script setup lang="ts">
/**
 * A selected line's menu (sketch 02·9, Q35): *Edit relation…*, *Straighten* — its hand bends dropped,
 * its ports kept, the router taking it round what is in the way — and *Move end to side ▸*, either end
 * onto any side of its element. The keyboard reaches every one; placing a bend freely is the pointer's
 * alone. Each command is one undoable step.
 */
import { computed, ref } from 'vue'
import type { Route, Side } from '../../domain/layout/orthogonal'
import type { End } from '../../domain/layout/lab/labRouteEdits'
import { lineAt, straightened, withEndAt, withRouteStated } from '../../domain/layout/lab/labRouteEdits'
import type { DiagramEditing } from '../composables/useDiagramEditing'
import CanvasMenu from './CanvasMenu.vue'
import type { CanvasMenuItem } from './canvasMenu'

const props = defineProps<{ editing: DiagramEditing; line: number }>()
const emit = defineEmits<{ edit: []; done: []; close: [] }>()

const SIDES: readonly Side[] = ['top', 'right', 'bottom', 'left']
const session = props.editing.session
const page = ref<'top' | 'sides'>('top')

const selected = computed(() => lineAt(session.geometry.value, session.arrangement.value, props.line))
const relation = computed(() => selected.value.relation)
const nameOf = (alias: string) => session.geometry.value?.elements.find((one) => one.alias === alias)?.label ?? alias
const stated = computed((): Route => selected.value.stated)
const sideNow = (end: End): Side | undefined =>
  stated.value[end]?.side
  ?? session.routes.value?.routes.get(String(props.line))?.[end === 'from' ? 'sourcePort' : 'targetPort'].side

const straighten = () => {
  const key = relation.value?.key
  if (key !== undefined) {
    session.change((_drawn, now) => withRouteStated(now, key, straightened(now.routes.get(key) ?? {})))
  }
  emit('done')
}

const moveEnd = (end: End, side: Side) => {
  const one = relation.value
  const key = one?.key
  if (!one || key === undefined) return
  session.change((_drawn, now, where) => {
    const alias = end === 'from' ? one.source : one.target
    const extent = where.elements.get(alias) ?? where.boxes.get(alias)
    if (!extent) return now
    return withRouteStated(now, key, withEndAt(now.routes.get(key) ?? {}, end, { side, at: 0.5 }, extent))
  })
  emit('done')
}

const capital = (side: Side) => side[0].toUpperCase() + side.slice(1)
const heading = computed(() => {
  const one = relation.value
  if (!one) return ''
  return page.value === 'top' ? `${nameOf(one.source)} → ${nameOf(one.target)}` : 'Move end to side'
})
const items = computed((): readonly CanvasMenuItem[] => {
  const one = relation.value
  if (!one) return []
  if (page.value === 'top') {
    return [
      { id: 'edit', label: 'Edit relation…', hint: 'its type, cardinalities, description and label',
        command: 'line.edit' },
      { id: 'straighten', label: 'Straighten', hint: 'remove every bend; routed round anything in the way',
        command: 'line.straighten',
        disabled: !stated.value.via?.length },
      { id: 'sides', label: 'Move end to side ▸', hint: 'either end, to any side of its element', command: 'line.move-end',
        disabled: one.key === undefined },
    ]
  }
  const ends = (['from', 'to'] as const).flatMap((end) => {
    const now = sideNow(end)
    return SIDES.map((side, at): CanvasMenuItem => ({
      id: `${end}:${side}`, label: capital(side), shortcut: side === now ? 'now' : undefined, command: 'line.move-end',
      caption: at === 0
        ? `${end === 'from' ? 'Source' : 'Target'} end · ${nameOf(end === 'from' ? one.source : one.target)}`
          + (now ? ` · now ${now}` : '')
        : undefined,
      attrs: { 'data-end': end, 'data-side': side, 'aria-current': side === now ? 'true' : undefined },
    }))
  })
  return [...ends, { id: 'back', label: '‹ Back', divider: true }]
})
const choose = (id: string) => {
  if (id === 'edit') emit('edit')
  else if (id === 'straighten') straighten()
  else if (id === 'sides') page.value = 'sides'
  else if (id === 'back') page.value = 'top'
  else {
    const [end, side] = id.split(':') as [End, Side]
    moveEnd(end, side)
  }
}
</script>

<template>
  <CanvasMenu
    :heading="heading"
    :label="page === 'top' ? 'Relation' : 'Move end to side'"
    :items="items"
    @choose="choose"
    @close="emit('close')"
  />
</template>
