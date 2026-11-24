<script setup lang="ts">
/**
 * What to put here — the canvas's one "act at this point" affordance.
 *
 * It replaces a **+ Add existing** button repeated once per frame. That button had to invent a
 * placement rule (offset by the frame's note count, modulo five) because it was anchored to a
 * frame rather than to a point; here the point *is* the gesture, which is the honest shape for a
 * canvas whose area membership is spatial. It also stops one capability costing one control per
 * frame, and it is where the rest of the canvas's per-point actions will go.
 *
 * Rendered outside the transformed layer, at fixed scale: a menu that shrank with the zoom would
 * be unreadable at exactly the moment someone is looking closely at something.
 *
 * Two states rather than two components — the search is what the second entry *opens into*, and
 * a person who picked "add existing" has not left the menu.
 */
import { computed, nextTick, ref, watch } from 'vue'
import EntityPickerInput from './EntityPickerInput.vue'
import CanvasMenu from './CanvasMenu.vue'
import type { CanvasMenuItem } from './canvasMenu'
import type { EntityDisplayInfo } from '../../domain'

const props = defineProps<{
  /** Viewport pixels from the canvas's top-left, or `null` when the menu is closed. */
  at: { x: number; y: number } | null
  /** The label of the frame the click fell in, for the heading. Empty when it fell outside one. */
  areaLabel: string
  /** The element types that frame permits. Empty means the frame narrows nothing. */
  permittedTypes: readonly string[]
  /** How many notes are selected. Lift acts on the selection, or on everything when none is. */
  selectionSize: number
  /** Whether this frame is the focused one, and whether there is a frame here to focus at all. */
  focused: boolean
  canFocus: boolean
}>()

const emit = defineEmits<{
  (event: 'new-note'): void
  (event: 'add-existing', entity: EntityDisplayInfo): void
  (event: 'lift'): void
  (event: 'focus-area'): void
  (event: 'close'): void
}>()

const searching = ref(false)
const root = ref<HTMLElement | null>(null)

// Every open starts on the actions, never on whatever the last one ended in.
watch(() => props.at, (at) => {
  searching.value = false
  if (at) void nextTick(() => root.value?.querySelector<HTMLElement>('[role="menuitem"]')?.focus())
})

/** `fixedEntityTypes` narrows the picker to what this frame permits — the same permitted set the
 * note panel offers first and a note outside it is warned about. An empty array is passed as
 * `undefined`: an area that permits everything must not be read as one that permits nothing. */
const scope = computed(() => (props.permittedTypes.length ? [...props.permittedTypes] : undefined))

const heading = computed(() =>
  props.areaLabel ? `Add to ${props.areaLabel}` : 'Add here',
)

/** The entries, drawn by the canvas menu every canvas opens; the lift acts on a selection made on the
 * canvas, so it belongs beside the thing it acts on rather than on a toolbar. */
const items = computed((): readonly CanvasMenuItem[] => [
  { id: 'new-note', label: 'New note', hint: 'or double-click', testid: 'menu-new-note' },
  { id: 'add-existing', label: 'Add existing element…', hint: 'bind what the model already has',
    testid: 'menu-add-existing' },
  ...props.canFocus
    ? [{
      id: 'focus', testid: 'menu-focus',
      label: props.focused ? 'Leave focus' : `Focus ${props.areaLabel}`,
      hint: props.focused ? 'show the whole canvas again' : 'fit the view to it; the rest fades back',
    }]
    : [],
  { id: 'lift', label: 'Lift into the model…', testid: 'menu-lift',
    hint: props.selectionSize ? `${props.selectionSize} selected` : 'everything on this scratchpad' },
])
const choose = (id: string) => {
  if (id === 'new-note') emit('new-note')
  else if (id === 'add-existing') searching.value = true
  else if (id === 'focus') emit('focus-area')
  else if (id === 'lift') emit('lift')
}
</script>

<template>
  <div
    v-if="at"
    ref="root"
    class="menu"
    data-testid="canvas-menu"
    :class="{ wide: searching }"
    :style="{ left: `${at.x}px`, top: `${at.y}px` }"
    @keydown.esc.stop="emit('close')"
    @pointerdown.stop
    @contextmenu.prevent.stop
  >
    <CanvasMenu
      v-if="!searching"
      :heading="heading"
      label="Add to the canvas"
      :items="items"
      @choose="choose"
      @close="emit('close')"
    />

    <div
      v-else
      class="search"
      data-testid="menu-search"
    >
      <p class="heading">
        {{ heading }}
      </p>
      <EntityPickerInput
        placeholder="Search the model by name or id…"
        widenable-to="none"
        close-on-select
        :fixed-entity-types="scope"
        @select="emit('add-existing', $event)"
      />
      <p
        v-if="scope"
        class="scoped"
      >
        Scoped to what this frame permits.
      </p>
    </div>
  </div>
</template>

<style scoped>
.menu {
  position: absolute; z-index: 6; min-width: 220px; outline: none;
  background: var(--surface); border: 1px solid var(--border-strong); border-radius: 8px; padding: 6px;
  box-shadow: var(--shadow); font-size: 12.5px;
}
.menu.wide { width: 380px; }
.heading {
  margin: 2px 6px 6px; font-size: 11px; text-transform: uppercase;
  letter-spacing: .05em; color: var(--faint);
}
.scoped { margin: 6px 2px 0; color: var(--faint); font-size: 11px; }
</style>
