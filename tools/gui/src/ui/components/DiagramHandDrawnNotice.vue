<script setup lang="ts">
/**
 * In edit mode, over a picture the server reads as drawn by hand (`written_by_hand`): one plain sentence on
 * what a save keeps and what it refuses, and where to go to change what the picture draws. What only the
 * hand-drawn picture has follows, collapsed.
 */
import type { HandDrawn } from '../../domain/schemas/handDrawn'
import DiagramHandDrawnDetails from './DiagramHandDrawnDetails.vue'

defineProps<{ handDrawn?: HandDrawn | undefined }>()
</script>

<template>
  <div
    class="kept-by-hand"
    role="note"
    data-testid="edit-body-by-hand"
  >
    <p>
      This diagram's picture is drawn by hand. Arranging it is saved; adding or removing what it draws is not.
      To change what it draws, leave editing and choose <em>Lay out automatically…</em>, which replaces the
      hand-drawn picture with a generated one.
    </p>
    <DiagramHandDrawnDetails :hand-drawn="handDrawn" />
  </div>
</template>

<style scoped>
.kept-by-hand { margin: 0 0 8px; padding: 6px 10px; border-left: 3px solid var(--accent); color: var(--muted); }
.kept-by-hand p { margin: 0; }
</style>
