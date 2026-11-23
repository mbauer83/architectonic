<script setup lang="ts">
/**
 * Integrating candidates (06·7): the analysis's candidates offered for integration (state
 * `candidate`) checked together for structural overlaps — the same element, field or relation
 * touched by more than one. Each overlap names its parties and their operations. A check is not a
 * merge, and no merge proves behaviour.
 */
import { computed, inject, ref, shallowRef } from 'vue'
import { Effect } from 'effect'
import type { IntegrationCheck } from '../../../domain/schemas/candidates'
import { modelServiceKey } from '../../keys'
import { formatEffectError } from '../../lib/errors'
import type { Candidates } from '../../composables/useCandidates'

const props = defineProps<{ candidates: Candidates; nameOf: (id: string) => string }>()
const svc = inject(modelServiceKey)!

const offered = computed(() => props.candidates.inAnalysis.value.filter((one) => one.state === 'candidate'))
const check = shallowRef<IntegrationCheck | null>(null)
const error = ref<string | null>(null)
const nameOfSet = (id: string): string => props.candidates.all.value.find((one) => one.id === id)?.name ?? id
const operationWords = (operation: Readonly<Record<string, unknown>>): string =>
  [operation.op, operation.field, operation.value].filter((part) => part !== undefined).map(String).join(' · ')

const run = async () => {
  try {
    check.value = await Effect.runPromise(svc.checkCandidates(offered.value.map((one) => one.id)))
    error.value = null
  } catch (failure) {
    error.value = formatEffectError(failure)
  }
}
</script>

<template>
  <div
    class="integration"
    data-testid="integration-tab"
  >
    <p class="lead">
      {{ offered.length }} candidate{{ offered.length === 1 ? '' : 's' }} offered for integration
      <span v-if="offered.length">: {{ offered.map((one) => one.name).join(', ') }}</span>.
    </p>
    <button
      type="button"
      class="btn btn-sm"
      :disabled="!offered.length"
      @click="run"
    >
      Check for overlaps
    </button>
    <div
      v-for="(overlap, index) in check?.overlaps ?? []"
      :key="index"
      class="conf"
    >
      <h4>{{ overlap.kind }}: {{ nameOf(overlap.subject) }}</h4>
      <div class="sides">
        <div
          v-for="party in overlap.parties"
          :key="party.set_id"
          class="side"
        >
          <small>{{ nameOfSet(party.set_id) }}</small>
          {{ operationWords(party.operation) }}
        </div>
      </div>
    </div>
    <p
      v-if="check && !check.overlaps.length"
      class="lead"
    >
      No overlaps between the offered candidates.
    </p>
    <p
      v-if="error"
      class="err"
      role="alert"
    >
      {{ error }}
    </p>
    <p class="foot">
      An overlap check compares what the candidates change, not how the result behaves. No merge proves
      behaviour.
    </p>
  </div>
</template>

<style scoped>
.integration { padding: 8px 10px; font-size: 12.5px; }
.lead { color: var(--text-2); margin: 0 0 8px; }
.conf { border: 1px solid var(--border); border-radius: 8px; margin: 8px 0; padding: 8px 10px; }
.conf h4 { font-size: 13px; margin: 0 0 4px; }
.sides { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.side { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; }
.side small { display: block; color: var(--muted); font-size: 11px; }
.foot { color: var(--muted); font-size: 11.5px; margin-top: 10px; }
.err { color: #b91c1c; }
</style>
