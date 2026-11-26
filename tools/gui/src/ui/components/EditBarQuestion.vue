<script setup lang="ts">
/**
 * A question the edit bar asks in place of its own buttons (sketch 01·7): leaving with unsaved changes,
 * or discarding them. The answers are the slot's buttons; the one marked `data-autofocus` — the safe
 * answer — takes the focus when the question is asked, so Enter on arrival loses nothing, and ← and →
 * move among them (`arrowsAcross`). Escape is answered by the edit mode, which knows what it cancels.
 */
import { onMounted, ref } from 'vue'
import { arrowsAcross } from '../lib/arrowsAcross'

defineProps<{ label: string }>()

const group = ref<HTMLElement | null>(null)
onMounted(() => group.value?.querySelector<HTMLElement>('[data-autofocus]')?.focus())
</script>

<template>
  <span
    ref="group"
    class="question"
    role="group"
    :aria-label="label"
    @keydown="arrowsAcross"
  >
    <slot />
  </span>
</template>

<style scoped>
.question {
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: 6px;
  background: var(--warn-soft); color: var(--warn-text); border: 1px solid var(--warn-border);
}
</style>
