<script setup lang="ts">
/**
 * "Download this, as…" — the ↓ that unfolds into the formats on offer.
 *
 * Presentational, and it decides nothing about what downloading means: it reports the format that
 * was chosen. A persisted diagram answers by navigating to its download address; the graph explorer
 * answers by serialising what is on screen. Both are the same affordance to a reader, and it used
 * to take a `diagramId` and construct that address itself — which is why the graph explorer arrived
 * with two bare buttons of its own instead, and looked like a different feature.
 */
import { ref } from 'vue'

const open = ref(false)
const emit = defineEmits<{ select: [format: 'png' | 'svg'] }>()

const choose = (format: 'png' | 'svg') => {
  open.value = false
  emit('select', format)
}
</script>

<template>
  <div class="dl-wrap">
    <!-- Glyph only, so the name is given rather than read: a `title` is not reliably an
         accessible name once the button has text content of its own, and "↓" is what that text
         is. The same reason the viewport controls carry one. -->
    <button
      class="dl-btn"
      title="Download"
      aria-label="Download"
      :aria-expanded="open"
      @click.stop.prevent="open = !open"
    >
      ↓
    </button>
    <div
      v-if="open"
      class="dl-overlay"
      @click.stop="open = false"
    />
    <div
      v-if="open"
      class="dl-dropdown"
    >
      <button
        class="dl-opt"
        @click.stop="choose('svg')"
      >
        SVG
      </button>
      <button
        class="dl-opt"
        @click.stop="choose('png')"
      >
        PNG
      </button>
    </div>
  </div>
</template>

<style scoped>
.dl-wrap { position: relative; display: inline-block; }
.dl-btn {
  padding: 3px 8px; border-radius: 4px; border: 1px solid #d1d5db;
  background: white; font-size: 12px; cursor: pointer; color: #6b7280; line-height: 1.4;
}
.dl-btn:hover { background: #f9fafb; color: #374151; }
.dl-overlay { position: fixed; inset: 0; z-index: 10; }
.dl-dropdown {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 11;
  background: white; border: 1px solid #e5e7eb; border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,.1); min-width: 90px; overflow: hidden;
}
.dl-opt {
  display: block; width: 100%; text-align: left; padding: 7px 12px;
  background: none; border: none; font-size: 13px; cursor: pointer; color: #374151;
}
.dl-opt:hover { background: #f9fafb; }
</style>
