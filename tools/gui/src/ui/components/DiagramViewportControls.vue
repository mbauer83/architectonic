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
defineProps<{
  /** Whether the view has been moved off its fitted framing, so a reset would do something. */
  isTransformed: boolean
  isFullscreen: boolean
  /** False where the document's permissions policy forbids fullscreen; the control is then absent
   *  rather than dead. */
  canFullscreen: boolean
  hint: string
}>()

defineEmits<{ reset: []; 'toggle-fullscreen': [] }>()
</script>

<template>
  <div class="viewport-controls">
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
  <div class="zoom-hint">
    {{ isFullscreen ? `${hint} · Esc to exit` : hint }}
  </div>
</template>

<style scoped>
.viewport-controls { position: absolute; top: 8px; right: 8px; display: flex; gap: 6px; }
.viewport-btn {
  /* Square, like the zoom cluster it now matches: a glyph in a box rather than a label in a pill. */
  width: 26px; height: 26px; display: inline-flex; align-items: center; justify-content: center;
  background: rgba(255, 255, 255, .92); border: 1px solid #d1d5db;
  border-radius: 5px; font-size: 14px; line-height: 1; cursor: pointer; color: #374151;
}
.viewport-btn:hover { background: white; }
.zoom-hint {
  position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%);
  font-size: 11px; color: #9ca3af; background: rgba(255, 255, 255, .8);
  padding: 2px 8px; border-radius: 4px; pointer-events: none; white-space: nowrap;
}
</style>
