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
}>()

const emit = defineEmits<{
  (event: 'new-note'): void
  (event: 'add-existing', entity: EntityDisplayInfo): void
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
</script>

<template>
  <div
    v-if="at"
    ref="root"
    class="menu"
    tabindex="-1"
    data-testid="canvas-menu"
    :class="{ wide: searching }"
    :style="{ left: `${at.x}px`, top: `${at.y}px` }"
    @keydown.esc.stop="emit('close')"
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
        data-testid="menu-new-note"
        @click="emit('new-note')"
      >
        New note
        <span class="hint">or double-click</span>
      </button>
      <button
        type="button"
        class="entry"
        data-testid="menu-add-existing"
        @click="searching = true"
      >
        Add existing element…
        <span class="hint">bind what the model already has</span>
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
