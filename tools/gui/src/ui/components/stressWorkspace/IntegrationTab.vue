<script setup lang="ts">
/**
 * Integrating adaptations (06·7, plan §3): the analysis's adaptations that stack on the naive architecture
 * chosen (those offered for integration first), integrated into a new candidate through the server's one
 * operation for it. The conflict cards are the candidates' own (`IntegrationCards`); here each party also says
 * what it answers in the analysis — its adaptation row, end states and stressors, each a link to its row.
 */
import { computed, inject, watch } from 'vue'
import type { WorkspaceTab } from '../../../domain/stressAnalysis/analysisProgress'
import { answerLinks } from '../../../domain/candidates/integration'
import { endStateName } from '../../../domain/stressAnalysis/analysisRows'
import { modelServiceKey, toastKey } from '../../keys'
import type { Candidates } from '../../composables/useCandidates'
import type { StressAnalysis } from '../../composables/useStressAnalysis'
import { useIntegration } from '../../composables/useIntegration'
import IntegrationCards from '../candidates/IntegrationCards.vue'

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

const linksOf = (candidate: string) =>
  answerLinks(candidate, props.analysis.adaptations.value, props.analysis.stressors.value)
const answersOf = (candidate: string): readonly string[] =>
  linksOf(candidate).endStates.map((row) => endStateName(props.analysis.endStates.value, row))
const toggle = (id: string, on: boolean) => {
  const now = integration.chosen.value.filter((one) => one !== id)
  void integration.choose(on ? [...now, id] : now)
}
/** An element by the name the naive architecture gives it. */
const nameOf = (id: string): string => props.analysis.nameOf(id)

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
    <IntegrationCards
      :integration="integration"
      :name-of="nameOf"
      :name-of-set="nameOfSet"
      :answers-of="answersOf"
    >
      <template #party="{ candidate }">
        <small class="links">
          <template
            v-for="row in linksOf(candidate).adaptations"
            :key="`a${row}`"
          >adaptation <a
            href="#"
            @click.prevent="emit('open', 'adaptations', row)"
          >{{ row }}</a> · </template>
          <template
            v-for="row in linksOf(candidate).endStates"
            :key="`e${row}`"
          >answers <a
            href="#"
            @click.prevent="emit('open', 'end-states', row)"
          >{{ endStateName(analysis.endStates.value, row) }}</a> · </template>
          <template
            v-for="row in linksOf(candidate).stressors"
            :key="`s${row}`"
          ><a
            href="#"
            @click.prevent="emit('open', 'stressors', row)"
          >{{ row }}</a>{{ ' ' }}</template>
        </small>
      </template>
    </IntegrationCards>
  </div>
</template>

<style scoped>
.integration { padding: 8px 10px; font-size: 12.5px; }
.chosen { border: none; margin: 0 0 8px; padding: 0; display: flex; flex-wrap: wrap; gap: 4px 14px; }
.chosen legend { font-weight: 600; margin-bottom: 4px; }
.chosen small, .none { color: var(--muted); }
.links { color: var(--muted); }
</style>
