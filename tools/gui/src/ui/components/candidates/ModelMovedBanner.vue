<script setup lang="ts">
/**
 * The "model moved" band (06·8): the candidate being read has operations the model moved under, by the
 * standing the comparison serves. *Re-base* is offered when an operation drifted, because only those
 * have a base to re-read; one with nothing to apply to is named with its reason, for its author to drop.
 */
import { computed, ref } from 'vue'
import type { OperationStanding } from '../../../domain/schemas/candidates'
import { hasMoved, modelMoved, movedSentence } from '../../../domain/candidates/modelMoved'
import PermittedButton from '../PermittedButton.vue'

const props = defineProps<{ name: string; standing: readonly OperationStanding[]; busy?: boolean }>()
const emit = defineEmits<{ rebase: [] }>()

const moved = computed(() => modelMoved(props.standing))
const open = ref(false)
const reasons = computed(() => [...moved.value.drifted, ...moved.value.conflicting])
</script>

<template>
  <div
    v-if="hasMoved(moved)"
    class="banner"
    role="status"
    data-testid="model-moved"
  >
    <div class="line">
      <b>Model moved:</b>
      <span>{{ name }} — {{ movedSentence(moved) }}</span>
      <span class="sp" />
      <button
        type="button"
        class="btn btn-plain btn-sm"
        :aria-expanded="open"
        @click="open = !open"
      >
        {{ open ? 'Hide them' : 'Show them' }}
      </button>
      <PermittedButton
        v-if="moved.drifted.length"
        operation="changes_rebase_candidate"
        class="btn btn-sm"
        data-testid="rebase"
        :disabled="busy"
        title="Write each drifted operation again against the model as it stands now, keeping what it asks for"
        @click="emit('rebase')"
      >
        Re-base
      </PermittedButton>
    </div>
    <ul v-if="open">
      <li
        v-for="(one, index) in reasons"
        :key="index"
      >
        <span :class="`standing standing--${one.standing}`">{{ one.standing }}</span> {{ one.reason }}
      </li>
    </ul>
  </div>
</template>

<style scoped>
.banner {
  margin: 6px 0 10px; padding: 7px 10px; border: 1px solid var(--warn-border);
  background: var(--warn-soft); color: var(--warn-text); border-radius: 6px; font-size: 12.5px;
}
.line { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.sp { flex: 1; }
ul { margin: 6px 0 0; padding-left: 18px; color: var(--text); }
li { margin: 2px 0; }
.standing { font-size: 11px; font-weight: 600; padding: 0 5px; border-radius: 3px; background: var(--surface); }
.standing--conflicting { color: var(--danger-strong); }
</style>
