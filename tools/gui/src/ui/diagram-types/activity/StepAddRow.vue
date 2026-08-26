<script setup lang="ts">
/**
 * The row of buttons that adds a step to a branch.
 *
 * One component because it appeared four times in `ActivityStepItem` — a decision's two arms, a
 * fork's branch, a partition's contents — spelled identically each time and differing only in which
 * handler each button called. Four copies of a list of step kinds is four places to forget one.
 *
 * The kinds come from `STEP_KEYS`, the same vocabulary the flat↔rich translation reads, so a kind
 * added to the notation appears here without an edit.
 */
import { STEP_KEYS, type StepKey } from './activityStepGraph'

defineEmits<{ add: [type: StepKey] }>()

/** Sentence case for a button, from the key the model uses. */
const label = (key: StepKey) => `+ ${key.charAt(0).toUpperCase()}${key.slice(1)}`
</script>

<template>
  <div class="add-row">
    <button
      v-for="key in STEP_KEYS"
      :key="key"
      class="add-btn"
      type="button"
      @click="$emit('add', key)"
    >
      {{ label(key) }}
    </button>
  </div>
</template>

<style scoped>
/* Carried verbatim from `ActivityStepItem`, where these buttons used to live. Scoped styles do not
   cross a component boundary, so moving the markup without the rules would have quietly restyled
   every add button in the editor. */
.add-row { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 2px; }
.add-btn {
  padding: 2px 7px;
  border: 1px solid #cbd5e1;
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 11px;
}
</style>
