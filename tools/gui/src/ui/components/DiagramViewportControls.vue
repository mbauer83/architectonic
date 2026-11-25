<script setup lang="ts">
/**
 * The chrome that sits over a pan/zoom diagram viewport: the corner controls and the gesture hint.
 *
 * One copy, because the diagram detail view, the viewpoint view and the assurance panel had carried
 * the same markup and the same CSS three times over — which is how the fullscreen control would
 * have been added three times too.
 *
 * Purely presentational: it reports what was pressed and knows nothing about panning, fitting or
 * what is being viewed.
 *
 * **Glyph only, so the name has to be given rather than read.** With the words gone the accessible
 * name can no longer come from the text, and `title` alone does not reliably supply one — hence the
 * explicit `aria-label` on each. The tooltip still carries the words for a sighted reader.
 *
 * **The two glyphs differ in shape, not in direction.** Framing and fullscreen are both "make this
 * fill the space" ideas and both ⛶ and ⤢ are read as fullscreen in the wild, so a framing control
 * drawn with either would be the fullscreen control twice. ⊙ recentres — a target, not an arrow —
 * against ⤢/⤡ for entering and leaving. The pair that *does* differ only in direction is entering
 * versus leaving fullscreen, which is safe: they are states of one control and only ever one shows.
 */
import { computed, ref } from 'vue'
import { useCanvasHostKeys } from '../composables/useCanvasHostKeys'
import { useEditingPreferences } from '../composables/useEditingPreferences'
import { zoomInKeyName } from '../lib/keyboardScheme'
import type { ViewportZoom } from './viewportZoom'

/** How far one press of − or + zooms (sketch 01·1). */
const BUTTON_STEP = 1.25

const props = defineProps<{
  /** The window's zoom, for the cluster at the bottom left (− 100 % + ⊙, sketch 01·1); none, no cluster. */
  zoom?: ViewportZoom
  /** Enter edit mode, which `E` asks for on the window; absent where it cannot be asked. */
  edit?: (() => void) | null
  /** Whether the view has been moved off its fitted framing, so a reset would do something. */
  isTransformed: boolean
  isFullscreen: boolean
  /** False where the document's permissions policy forbids fullscreen; the control is then absent
   *  rather than dead. */
  canFullscreen: boolean
  hint: string
}>()

defineEmits<{ reset: []; 'toggle-fullscreen': [] }>()

const prefs = useEditingPreferences()
// The cluster's keys belong to the window it sits in: they are answered wherever its focus is inside it.
const controls = ref<HTMLElement | null>(null)
const host = computed(() => controls.value?.parentElement ?? null)
useCanvasHostKeys(host, () => props.zoom, () => props.edit ?? null)
const percent = computed(() => (props.zoom ? `${Math.round(props.zoom.scale.value * 100)}%` : ''))
</script>

<template>
  <div
    ref="controls"
    class="viewport-controls"
  >
    <button
      v-if="isTransformed"
      class="viewport-btn"
      title="Reset view"
      aria-label="Reset view"
      @click.stop="$emit('reset')"
    >
      ⊙
    </button>
    <!-- Last, so it keeps its place when Reset appears and disappears beside it. -->
    <button
      v-if="canFullscreen"
      class="viewport-btn"
      :title="isFullscreen ? 'Exit fullscreen (Esc)' : 'View fullscreen'"
      :aria-label="isFullscreen ? 'Exit fullscreen' : 'View fullscreen'"
      @click.stop="$emit('toggle-fullscreen')"
    >
      {{ isFullscreen ? '⤡' : '⤢' }}
    </button>
  </div>
  <div
    v-if="zoom"
    class="zoom-cluster"
    role="group"
    aria-label="Zoom"
    data-testid="zoom-cluster"
  >
    <button
      type="button"
      title="Zoom out (−)"
      aria-label="Zoom out"
      data-testid="zoom-out"
      @click.stop="zoom.zoomBy(1 / BUTTON_STEP)"
    >
      −
    </button>
    <output
      class="zoom-cluster__percent"
      data-testid="zoom-percent"
    >{{ percent }}</output>
    <button
      type="button"
      :title="`Zoom in (${zoomInKeyName(prefs.scheme.value)})`"
      aria-label="Zoom in"
      data-testid="zoom-in"
      @click.stop="zoom.zoomBy(BUTTON_STEP)"
    >
      +
    </button>
    <button
      type="button"
      title="Fit the diagram (0)"
      aria-label="Fit the diagram"
      data-testid="zoom-fit"
      @click.stop="zoom.resetView()"
    >
      ⊙
    </button>
  </div>
  <div class="zoom-hint">
    {{ isFullscreen ? `${hint} · Esc to exit` : hint }}
  </div>
</template>

<style scoped>
/* Above a docked sidebar (z-index 2 in `styles/shared.css`), which is teleported into the same
   fullscreen host and would otherwise be painted over these — leaving the control that *leaves*
   fullscreen unreachable behind the panel. */
.viewport-controls { position: absolute; top: 8px; right: 8px; z-index: 3; display: flex; gap: 6px; }
.viewport-btn {
  /* Square, like the zoom cluster it now matches: a glyph in a box rather than a label in a pill. */
  width: 26px; height: 26px; display: inline-flex; align-items: center; justify-content: center;
  background: var(--overlay); border: 1px solid var(--border-strong);
  border-radius: 5px; font-size: 14px; line-height: 1; cursor: pointer; color: var(--text-2);
}
.viewport-btn:hover { background: var(--surface); }
/* The zoom cluster, bottom left: the overview has the bottom right. */
.zoom-cluster {
  position: absolute; left: 8px; bottom: 28px; z-index: 3; display: flex; align-items: center;
  background: var(--overlay); border: 1px solid var(--border-strong); border-radius: 5px; color: var(--text-2);
}
.zoom-cluster button {
  width: 26px; height: 26px; border: none; background: none; cursor: pointer; font-size: 14px; color: inherit;
}
.zoom-cluster button:hover { background: var(--surface); }
.zoom-cluster__percent { min-width: 40px; text-align: center; font-size: 11px; color: var(--muted); }
.zoom-hint {
  position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%);
  font-size: 11px; color: var(--muted); background: var(--overlay);
  padding: 2px 8px; border-radius: 4px; pointer-events: none; white-space: nowrap;
}
</style>
