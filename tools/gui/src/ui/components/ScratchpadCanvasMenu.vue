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
  if (at) void nextTick(() => root.value?.focus())
})

/** `fixedEntityTypes` narrows the picker to what this frame permits — the permitted set doing the
 * second half of its job, having already narrowed the type picker. An empty array is passed as
 * `undefined`: an area that permits everything must not be read as one that permits nothing. */
const scope = computed(() => (props.permittedTypes.length ? [...props.permittedTypes] : undefined))

const heading = computed(() =>
  props.areaLabel ? `Add to ${props.areaLabel}` : 'Add here',
)

/** Arrow keys walk the entries, because a `menu` that only answered Tab would be a menu in name.
 * The menu itself holds focus until an entry is reached, so the first press lands on the first. */
const move = (step: number): void => {
  const entries = [...(root.value?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])]
  if (!entries.length) return
  const here = entries.indexOf(window.document.activeElement as HTMLElement)
  const next = here < 0 ? (step > 0 ? 0 : entries.length - 1) : (here + step + entries.length) % entries.length
  entries[next]?.focus()
}
</script>

<template>
  <div
    v-if="at"
    ref="root"
    class="menu"
    role="menu"
    tabindex="-1"
    aria-label="Add to the canvas"
    data-testid="canvas-menu"
    :class="{ wide: searching }"
    :style="{ left: `${at.x}px`, top: `${at.y}px` }"
    @keydown.esc.stop="emit('close')"
    @keydown.down.prevent="move(1)"
    @keydown.up.prevent="move(-1)"
    @pointerdown.stop
    @contextmenu.prevent.stop
  >
    <p class="heading">
      {{ heading }}
    </p>

    <template v-if="!searching">
      <button
        type="button"
        class="entry"
        role="menuitem"
        data-testid="menu-new-note"
        @click="emit('new-note')"
      >
        New note
        <span class="hint">or double-click</span>
      </button>
      <button
        type="button"
        class="entry"
        role="menuitem"
        data-testid="menu-add-existing"
        @click="searching = true"
      >
        Add existing element…
        <span class="hint">bind what the model already has</span>
      </button>
      <button
        v-if="canFocus"
        type="button"
        class="entry"
        role="menuitem"
        data-testid="menu-focus"
        @click="emit('focus-area')"
      >
        {{ focused ? 'Leave focus' : `Focus ${areaLabel}` }}
        <span class="hint">{{
          focused ? 'show the whole canvas again' : 'fit the view to it; the rest fades back'
        }}</span>
      </button>
      <!-- Here rather than on a toolbar: lift acts on a selection made on the canvas, so the act
           belongs beside the thing it acts on. -->
      <button
        type="button"
        class="entry"
        role="menuitem"
        data-testid="menu-lift"
        @click="emit('lift')"
      >
        Lift into the model…
        <span class="hint">{{
          selectionSize ? `${selectionSize} selected` : 'everything on this scratchpad'
        }}</span>
      </button>
    </template>

    <div
      v-else
      class="search"
      data-testid="menu-search"
    >
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
  background: #fff; border: 1px solid #d1d5db; border-radius: 8px; padding: 6px;
  box-shadow: 0 8px 24px rgba(0,0,0,.12); font-size: 12.5px;
}
.menu.wide { width: 380px; }
.heading {
  margin: 2px 6px 6px; font-size: 11px; text-transform: uppercase;
  letter-spacing: .05em; color: #9ca3af;
}
.entry {
  display: block; width: 100%; text-align: left; border: none; background: none;
  padding: 6px 8px; border-radius: 5px; cursor: pointer; color: #1f2328; font-size: 12.5px;
}
.entry:hover, .entry:focus-visible { background: #f3f4f6; }
.hint { display: block; color: #9ca3af; font-size: 11px; }
.scoped { margin: 6px 2px 0; color: #9ca3af; font-size: 11px; }
</style>
