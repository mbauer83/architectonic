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

const props = defineProps<{ editing: DiagramEditing; line: number }>()
const emit = defineEmits<{ edit: []; done: [] }>()

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
</script>

<template>
  <div
    class="line-menu"
    role="menu"
    :aria-label="page === 'top' ? 'Relation' : 'Move end to side'"
  >
    <template v-if="page === 'top' && relation">
      <strong>{{ nameOf(relation.source) }} → {{ nameOf(relation.target) }}</strong>
      <button
        role="menuitem"
        @click="emit('edit')"
      >
        Edit relation…
      </button>
      <button
        role="menuitem"
        :disabled="!stated.via?.length"
        title="remove every bend; routed round anything in the way"
        @click="straighten"
      >
        Straighten
      </button>
      <button
        role="menuitem"
        :disabled="relation.key === undefined"
        title="either end, to any side of its element"
        @click="page = 'sides'"
      >
        Move end to side ▸
      </button>
    </template>
    <template v-else-if="relation">
      <template
        v-for="end in (['from', 'to'] as const)"
        :key="end"
      >
        <p class="line-menu__end">
          {{ end === 'from' ? 'Source' : 'Target' }} end ·
          {{ nameOf(end === 'from' ? relation.source : relation.target) }}
        </p>
        <button
          v-for="side in SIDES"
          :key="side"
          role="menuitem"
          :aria-current="side === sideNow(end) ? 'true' : undefined"
          :data-end="end"
          :data-side="side"
          @click="moveEnd(end, side)"
        >
          {{ side[0].toUpperCase() + side.slice(1) }}{{ side === sideNow(end) ? ' · now' : '' }}
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
.line-menu button,
.line-menu strong { display: block; margin-block: 0.25rem; }
.line-menu__end { margin: 0.5rem 0 0.1rem; font-size: 0.85em; opacity: 0.8; }
</style>
