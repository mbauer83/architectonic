<script setup lang="ts">
/**
 * One menu opened at a point on a canvas (sketch 03·5): a heading in small capitals, then entries each
 * with a label, an optional muted hint under it and an optional key at the right, groups split by a
 * rule, the destructive entry in the danger colour. It opens on its first entry; the arrows walk the
 * entries and wrap, Home and End go to the ends, Enter or Space chooses, Escape asks to close.
 *
 * It draws the entries only: the surface it sits on — fixed at a point, or inside a canvas — is the
 * caller's, so the diagram editor and the scratchpad open the same menu on their own surfaces.
 */
import { nextTick, onMounted, ref, useId, watch } from 'vue'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import { toGlyphKey } from '../lib/glyphKey'
import { type CanvasMenuItem, menuStep } from './canvasMenu'

const props = defineProps<{
  items: readonly CanvasMenuItem[]
  /** What the menu acts on, in the heading: an element's name, "3 selected", "Add here". */
  heading?: string
  /** The element type the heading names, drawn as its glyph and name after it. */
  type?: string
  /** The menu's accessible name; the heading when absent. */
  label?: string
}>()
const emit = defineEmits<{ choose: [id: string]; close: [] }>()

const root = ref<HTMLElement | null>(null)
// The label names an entry and the hint describes it, so a reader hears "Distribute ▸", then why.
const uid = useId()
const idOf = (item: CanvasMenuItem, part: string) => `${uid}-${part}-${item.id}`
const entries = () => [...root.value?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []]
const focusFirst = () => void nextTick(() => entries()[0]?.focus())
onMounted(focusFirst)
// A submenu replaces the entries in place: focus starts on its first, as it did on the menu's.
watch(() => props.items.map((one) => one.id).join('\n'), focusFirst)

const key = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    emit('close')
    return
  }
  const all = entries()
  const next = menuStep(event.key, all.indexOf(document.activeElement as HTMLElement), all.length)
  if (next === null) return
  event.preventDefault()
  all[next]?.focus()
}
const choose = (item: CanvasMenuItem) => {
  if (!item.disabled) emit('choose', item.id)
}
</script>

<template>
  <div
    ref="root"
    class="canvas-menu"
    role="menu"
    :aria-label="label ?? heading"
    @keydown="key"
  >
    <p
      v-if="heading"
      class="canvas-menu__heading"
    >
      {{ heading }}<template v-if="type">
        ·
        <span class="canvas-menu__type">
          <ArchimateTypeGlyph
            :type="toGlyphKey(type)"
            :size="14"
          />{{ type.replace(/-/g, ' ') }}
        </span>
      </template>
    </p>
    <template
      v-for="item in items"
      :key="item.id"
    >
      <div
        v-if="item.divider"
        class="canvas-menu__sep"
        role="separator"
      />
      <p
        v-if="item.caption"
        class="canvas-menu__caption"
      >
        {{ item.caption }}
      </p>
      <button
        type="button"
        class="canvas-menu__entry"
        :class="{ 'canvas-menu__entry--danger': item.danger }"
        role="menuitem"
        tabindex="-1"
        :aria-disabled="item.disabled ? 'true' : undefined"
        :aria-labelledby="idOf(item, 'l')"
        :aria-describedby="item.hint ? idOf(item, 'h') : undefined"
        :data-testid="item.testid"
        v-bind="item.attrs"
        @click="choose(item)"
      >
        <span class="canvas-menu__grow">
          <span :id="idOf(item, 'l')">{{ item.label }}</span>
          <span
            v-if="item.hint"
            :id="idOf(item, 'h')"
            class="canvas-menu__hint"
          >{{ item.hint }}</span>
        </span>
        <span
          v-if="item.shortcut"
          class="canvas-menu__key"
        >{{ item.shortcut }}</span>
      </button>
    </template>
  </div>
</template>

<style scoped>
.canvas-menu { outline: none; font-size: 12.5px; }
.canvas-menu__heading {
  margin: 2px 6px 6px; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--faint);
}
.canvas-menu__type {
  display: inline-flex; align-items: center; gap: 3px; text-transform: none; letter-spacing: 0;
}
.canvas-menu__type :deep(svg) { vertical-align: -2px; }
.canvas-menu__caption { margin: 6px 6px 2px; font-size: 11px; color: var(--faint); }
.canvas-menu__entry {
  display: flex; align-items: center; gap: 7px; width: 100%; text-align: left; border: none;
  background: none; padding: 6px 8px; border-radius: 5px; cursor: pointer; color: var(--text);
  font: inherit; font-size: 12.5px;
}
.canvas-menu__entry:hover, .canvas-menu__entry:focus-visible, .canvas-menu__entry:focus {
  background: var(--soft); outline: none;
}
.canvas-menu__entry[aria-disabled="true"] { color: var(--faint); cursor: default; }
.canvas-menu__entry[aria-disabled="true"]:hover { background: none; }
.canvas-menu__entry--danger { color: var(--danger-strong); }
.canvas-menu__grow { flex: 1; min-width: 0; }
.canvas-menu__hint { display: block; color: var(--faint); font-size: 11px; }
.canvas-menu__key { color: var(--faint); font: 11px ui-monospace, monospace; white-space: nowrap; padding-left: 12px; }
.canvas-menu__sep { height: 1px; background: var(--hair); margin: 4px 0; }
</style>
