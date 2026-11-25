<script setup lang="ts">
/**
 * Integrating chosen candidates into a new one (06·7, S4), wherever candidates are chosen: the stress
 * workspace's Integration tab and the comparison page. Each conflict between them is a card naming its parties
 * and what each proposes, with the actions it permits — take this side, drop this change, merge a value, or
 * raise a decision as a draft ADR — over the server's one operation for it (`useIntegration`). What a party
 * answers in an analysis is the caller's to show, in the `party` slot, and to name for a decision (*answersOf*).
 * No merge proves behaviour, and the cards say so.
 */
import { computed, reactive } from 'vue'
import type { IntegrationConflict } from '../../../domain/schemas/candidates'
import {
  conflictSubject, conflictTitle, mergedResolution, partyResolution, permits, proposal, resolutionWords,
} from '../../../domain/candidates/integration'
import { documentDetailRoute } from '../../router/artifactRoutes'
import type { Integration } from '../../composables/useIntegration'
import PermittedButton from '../PermittedButton.vue'

const props = withDefaults(defineProps<{
  integration: Integration
  /** An element by the name the reader knows it by. */
  nameOf: (id: string) => string
  /** A candidate by its name. */
  nameOfSet: (id: string) => string
  /** What a party answers, by name, for the decision a conflict raises. */
  answersOf?: (candidate: string) => readonly string[]
}>(), { answersOf: () => [] })

const conflicts = computed(() => props.integration.answer.value?.conflicts ?? [])
const merged = reactive<Record<string, string>>({})
const about = (conflict: IntegrationConflict): string => conflictSubject(conflict, props.nameOf)
const mergeIn = (conflict: IntegrationConflict) =>
  props.integration.resolve(mergedResolution(conflict, merged[conflict.subject] ?? ''), about(conflict))
const raise = (conflict: IntegrationConflict) => props.integration.raiseDecision(conflict, conflict.parties.map(
  (party) => ({
    name: props.nameOfSet(party.set_id), proposes: proposal(party.operation, props.nameOf),
    answers: props.answersOf(party.set_id),
  }),
), props.nameOf)
</script>

<template>
  <div class="integration-cards">
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
          <slot
            name="party"
            :candidate="party.set_id"
          />
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
      <label>Name <input
        :value="integration.name.value"
        @input="integration.rename(($event.target as HTMLInputElement).value)"
      ></label>
      <PermittedButton
        operation="changes_integrate_candidates"
        class="btn btn-sm btn-primary"
        data-testid="integrate"
        :disabled="!integration.ready.value"
        @click="integration.integrate()"
      >
        Integrate
      </PermittedButton>
    </footer>
    <p class="foot">
      Integrating compares what the candidates change, not how the result behaves. No merge proves behaviour; the
      test set judges the integration.
    </p>
  </div>
</template>

<style scoped>
.lead { color: var(--text-2); margin: 0 0 8px; }
.settled { margin: 0 0 8px; padding-left: 18px; color: var(--text-2); }
.settled li { margin: 2px 0; }
.conf { margin: 8px 0; padding: 8px 10px; }
.conf h4 { font-size: 13px; margin: 0 0 6px; }
.sides { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; }
.side { display: flex; flex-direction: column; gap: 4px; border: 1px solid var(--border); border-radius: 6px;
  padding: 6px 8px; }
.acts { display: flex; gap: 6px; flex-wrap: wrap; }
.merge, .decide { display: flex; gap: 8px; align-items: center; margin: 8px 0 0; flex-wrap: wrap; }
.merge input, footer input { font: inherit; margin-left: 4px; }
.decide small { color: var(--muted); }
footer { display: flex; gap: 8px; align-items: center; margin-top: 10px; }
.foot { color: var(--muted); font-size: 11.5px; margin-top: 10px; }
.err { color: var(--danger-strong); }
</style>
