<script setup lang="ts">
/**
 * Deleting an element from the model asks first (sketch 03·6): the question in the page's words, that
 * it is undoable until Save, and — where the canvas can — taking it off this diagram only, instead.
 * Cancel holds the focus, so Enter on arrival deletes nothing.
 */
import type { CanvasWords } from './canvasWords'

defineProps<{ name: string; words: CanvasWords }>()
const emit = defineEmits<{ confirm: []; remove: []; cancel: [] }>()
</script>

<template>
  <div class="cp-form">
    <h3 class="cp-title">
      {{ words.deleteQuestion(name) }}
    </h3>
    <p class="cp-note">
      It joins this edit session; until Save, Undo brings it back.
    </p>
    <div class="cp-row-end">
      <button
        type="button"
        class="cp-btn"
        data-autofocus
        @click="emit('cancel')"
      >
        Cancel
      </button>
      <button
        v-if="words.removeEntry"
        type="button"
        class="cp-btn"
        @click="emit('remove')"
      >
        {{ words.removeEntry }} instead
      </button>
      <button
        type="button"
        class="cp-btn cp-btn--danger"
        @click="emit('confirm')"
      >
        {{ words.deleteConfirm }}
      </button>
    </div>
  </div>
</template>
