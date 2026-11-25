<script setup lang="ts">
/**
 * Integrating adaptations (06·7, plan §3): the analysis's adaptations that stack on the naive architecture
 * chosen (those offered for integration first), integrated into a new candidate through the server's one
 * operation for it. Each conflict between them is a card naming its parties, what each proposes and what
 * each answers in the analysis — its adaptation row, end states and stressors, each a link to its row — with
 * the actions it permits: take this side, drop this change, merge a value, or raise a decision as a draft ADR.
 * Every resolution is asked of the server at once, so the cards are always the conflicts still standing.
 * No merge proves behaviour, and the tab says so.
 */
import { computed, inject, reactive, watch } from 'vue'
import type { WorkspaceTab } from '../../../domain/stressAnalysis/analysisProgress'
import type { IntegrationConflict } from '../../../domain/schemas/candidates'
import {
  answerLinks, conflictSubject, conflictTitle, mergedResolution, partyResolution, permits, proposal,
  resolutionWords,
} from '../../../domain/candidates/integration'
import { endStateName } from '../../../domain/stressAnalysis/analysisRows'
import { modelServiceKey, toastKey } from '../../keys'
import { documentDetailRoute } from '../../router/artifactRoutes'
import type { Candidates } from '../../composables/useCandidates'
import type { StressAnalysis } from '../../composables/useStressAnalysis'
import { useIntegration } from '../../composables/useIntegration'

const props = defineProps<{ candidates: Candidates; analysis: StressAnalysis }>()
const emit = defineEmits<{ open: [tab: WorkspaceTab, row: string] }>()
const svc = inject(modelServiceKey)!
const toast = inject(toastKey, () => undefined)

/** The adaptations that may be integrated: drafts and offered candidates on the naive architecture. */
const integrable = computed(() => props.candidates.inStack.value.filter((one) =>
  one.parent === props.analysis.naiveId.value && (one.state === 'draft' || one.state === 'candidate')))
const nameOfSet = (id: string): string => props.candidates.all.value.find((one) => one.id === id)?.name ?? id
const integration = useIntegration(svc, (id) => {
  toast(`Integrated into ${integration.name.value}, a new candidate on the naive architecture.`)
  void props.candidates.load()
  void props.candidates.select(id)
})
const conflicts = computed(() => integration.answer.value?.conflicts ?? [])
const merged = reactive<Record<string, string>>({})

const linksOf = (candidate: string) =>
  answerLinks(candidate, props.analysis.adaptations.value, props.analysis.stressors.value)
const toggle = (id: string, on: boolean) => {
  const now = integration.chosen.value.filter((one) => one !== id)
  void integration.choose(on ? [...now, id] : now)
}
const raise = (conflict: IntegrationConflict) => integration.raiseDecision(conflict, conflict.parties.map((party) => ({
  name: nameOfSet(party.set_id), proposes: proposal(party.operation, nameOf),
  answers: linksOf(party.set_id).endStates.map((row) => endStateName(props.analysis.endStates.value, row)),
})), nameOf)
/** An element by the name the naive architecture gives it. */
const nameOf = (id: string): string => props.analysis.nameOf(id)
const about = (conflict: IntegrationConflict): string => conflictSubject(conflict, nameOf)
const mergeIn = (conflict: IntegrationConflict) =>
  integration.resolve(mergedResolution(conflict, merged[conflict.subject] ?? ''), about(conflict))

// Those offered for integration are chosen when the adaptations are first read; the author may change it.
watch(() => integrable.value.map((one) => one.id).join(' '), () => {
  if (integration.chosen.value.length || integration.answer.value) return
  void integration.choose(integrable.value.filter((one) => one.state === 'candidate').map((one) => one.id))
}, { immediate: true })
</script>

<template>
  <div
    class="integration"
    data-testid="integration-tab"
  >
    <fieldset class="chosen">
      <legend>Integrate these adaptations into a new candidate</legend>
      <label
        v-for="one in integrable"
        :key="one.id"
      ><input
        type="checkbox"
        :checked="integration.chosen.value.includes(one.id)"
        :data-testid="`integrate-${one.id}`"
        @change="toggle(one.id, ($event.target as HTMLInputElement).checked)"
      > {{ one.name }} <small>{{ one.state === 'candidate' ? 'offered' : 'draft' }}</small></label>
      <p
        v-if="!integrable.length"
        class="none"
      >
        No adaptation stacks on the naive architecture yet.
      </p>
    </fieldset>
    <p
      v-if="integration.answer.value"
      class="lead"
      data-testid="integration-standing"
    >
      {{ conflicts.length
        ? `${conflicts.length} conflict${conflicts.length === 1 ? '' : 's'} to settle before integrating.`
        : `No conflict stands: the integration holds ${integration.answer.value.operations} operations.` }}
    </p>
    <ol
      v-if="integration.resolutions.value.length"
      class="settled"
      aria-label="Settled"
    >
      <li
        v-for="(one, index) in integration.resolutions.value"
        :key="index"
      >
        {{ resolutionWords(one, nameOfSet, integration.abouts.value[index] ?? one.subject) }}
        <button
          type="button"
          class="btn btn-sm"
          @click="integration.takeBack(index)"
        >
          Take back
        </button>
      </li>
    </ol>
    <section
      v-for="conflict in conflicts"
      :key="`${conflict.kind} ${conflict.subject}`"
      class="conf card"
      data-testid="integration-conflict"
    >
      <h4>{{ conflictTitle(conflict, nameOf) }}</h4>
      <div class="sides">
        <div
          v-for="party in conflict.parties"
          :key="party.set_id"
          class="side"
        >
          <b>{{ nameOfSet(party.set_id) }}</b>
          <span>{{ proposal(party.operation, nameOf) }}</span>
          <small class="links">
            <template
              v-for="row in linksOf(party.set_id).adaptations"
              :key="`a${row}`"
            >adaptation <a
              href="#"
              @click.prevent="emit('open', 'adaptations', row)"
            >{{ row }}</a> · </template>
            <template
              v-for="row in linksOf(party.set_id).endStates"
              :key="`e${row}`"
            >answers <a
              href="#"
              @click.prevent="emit('open', 'end-states', row)"
            >{{ endStateName(analysis.endStates.value, row) }}</a> · </template>
            <template
              v-for="row in linksOf(party.set_id).stressors"
              :key="`s${row}`"
            ><a
              href="#"
              @click.prevent="emit('open', 'stressors', row)"
            >{{ row }}</a>{{ ' ' }}</template>
          </small>
          <span class="acts">
            <button
              type="button"
              class="btn btn-sm"
              data-testid="take-side"
              :disabled="integration.busy.value"
              @click="integration.resolve(partyResolution(conflict, 'take', party.set_id), about(conflict))"
            >Take this side</button>
            <button
              type="button"
              class="btn btn-sm"
              data-testid="drop-change"
              :disabled="integration.busy.value"
              @click="integration.resolve(partyResolution(conflict, 'drop', party.set_id), about(conflict))"
            >Drop this change</button>
          </span>
        </div>
      </div>
      <form
        v-if="permits(conflict, 'merge')"
        class="merge"
        @submit.prevent="mergeIn(conflict)"
      >
        <label>Merged value <input
          v-model="merged[conflict.subject]"
          data-testid="merged-value"
        ></label>
        <button
          type="submit"
          class="btn btn-sm"
          :disabled="integration.busy.value || !merged[conflict.subject]"
        >
          Use this value
        </button>
      </form>
      <p class="decide">
        <RouterLink
          v-if="integration.decisions.value.get(conflict.subject)"
          :to="documentDetailRoute(integration.decisions.value.get(conflict.subject) ?? '')"
        >Decision drafted</RouterLink>
        <button
          v-else
          type="button"
          class="btn btn-sm"
          data-testid="raise-decision"
          @click="raise(conflict)"
        >
          Raise a decision…
        </button>
        <small>A draft ADR with each side as an option; the conflict stays until it is settled here.</small>
      </p>
    </section>
    <p
      v-if="integration.error.value"
      class="err"
      role="alert"
    >
      {{ integration.error.value }}
    </p>
    <footer>
      <label>Name <input v-model="integration.name.value"></label>
      <button
        type="button"
        class="btn btn-sm btn-primary"
        data-testid="integrate"
        :disabled="!integration.ready.value"
        @click="integration.integrate()"
      >
        Integrate
      </button>
    </footer>
    <p class="foot">
      Integrating compares what the candidates change, not how the result behaves. No merge proves behaviour; the
      test set judges the integration.
    </p>
  </div>
</template>

<style scoped>
.integration { padding: 8px 10px; font-size: 12.5px; }
.chosen { border: none; margin: 0 0 8px; padding: 0; display: flex; flex-wrap: wrap; gap: 4px 14px; }
.chosen legend { font-weight: 600; margin-bottom: 4px; }
.chosen small, .none { color: var(--muted); }
.lead { color: var(--text-2); margin: 0 0 8px; }
.settled { margin: 0 0 8px; padding-left: 18px; color: var(--text-2); }
.settled li { margin: 2px 0; }
.conf { margin: 8px 0; padding: 8px 10px; }
.conf h4 { font-size: 13px; margin: 0 0 6px; }
.sides { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; }
.side { display: flex; flex-direction: column; gap: 4px; border: 1px solid var(--border); border-radius: 6px;
  padding: 6px 8px; }
.links { color: var(--muted); }
.acts { display: flex; gap: 6px; flex-wrap: wrap; }
.merge, .decide { display: flex; gap: 8px; align-items: center; margin: 8px 0 0; flex-wrap: wrap; }
.merge input, footer input { font: inherit; margin-left: 4px; }
.decide small { color: var(--muted); }
footer { display: flex; gap: 8px; align-items: center; margin-top: 10px; }
.foot { color: var(--muted); font-size: 11.5px; margin-top: 10px; }
.err { color: var(--danger-strong); }
</style>
