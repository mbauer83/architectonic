<script setup lang="ts">
import { ref, computed } from 'vue'
import type { useWizardSession } from '../composables/useWizardSession'
import type { AuthoringGuidance } from '../../domain'
import type { DomainQuestionnaire } from '../lib/wizardQuestionnaires'
import { entityTypesForDomain } from './WizardDomainStage.helpers'
import { withArticle } from '../lib/indefiniteArticle'
import WizardEntityStage from './WizardEntityStage.vue'

/**
 * A questionnaire is a menu of prompts, not a rail: every question is skippable, the step chips
 * jump anywhere, and a step accepts several entities ("+ Add another") — so "a requirement
 * without a stakeholder" or "three affected processes" are one click away. Only answered steps
 * feed the spine's proximity anchors. Completion offers every goal-labeled bridge the domain
 * has (an omnidirectional spine — no fixed next domain).
 */
const props = defineProps<{
  questionnaire: DomainQuestionnaire
  guidance: AuthoringGuidance | null
  session: ReturnType<typeof useWizardSession>
}>()
const emit = defineEmits<{ exit: [] }>()

const stepIndex = ref(0)
const answeredCounts = ref<Map<number, number>>(new Map())

const currentStep = computed(() => props.questionnaire.steps[stepIndex.value])
const isLastStep = computed(() => stepIndex.value === props.questionnaire.steps.length - 1)
const complete = computed(() => stepIndex.value >= props.questionnaire.steps.length)

const currentTypeGuidance = computed(() => {
  if (!currentStep.value) return undefined
  return entityTypesForDomain(props.guidance, props.questionnaire.domain)
    .find((t) => t.name === currentStep.value.entityType)
})

// The wizard teaches modeling in the ArchiMate domains: only the domain's own framing
// and the entity-type/specialization guidance belong here. Workspace- and
// meta-ontology-level context is delivered by broader guidance surfaces, not per question.
const WIZARD_CONTEXT_LEVELS = new Set(['domain', 'entity_type', 'specialization'])
const wizardContextLayers = computed(() =>
  (currentTypeGuidance.value?.context ?? []).filter((layer) => WIZARD_CONTEXT_LEVELS.has(layer.level)))
// Label levels for readers; a meta-ontology layer (if a surface ever shows one) is titled
// by its alias ("Archimate-4"), never by the internal level id "meta_ontology".
const contextLevelLabel = (layer: { level: string; node: string }): string =>
  layer.level === 'meta_ontology'
    ? layer.node.split(/[-_]/).map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join('-')
    : layer.level.replace(/_/g, ' ')

// Anchors live in the session, not locally: a bridge to the next domain's questionnaire keeps
// the whole cross-domain spine (motivation chain → business actors → …) as ranking context.
const spineAnchors = computed(() => [...props.session.state.spineAnchorIds])

const recordAnswer = (entity: { id: string; name: string }) => {
  props.session.recordSpineAnchor(entity.id)
  answeredCounts.value.set(stepIndex.value, (answeredCounts.value.get(stepIndex.value) ?? 0) + 1)
}

const onStepDone = (entity: { id: string; name: string } | null) => {
  if (!entity) { emit('exit'); return }
  recordAnswer(entity)
  stepIndex.value += 1
}

const onStepAnother = (entity: { id: string; name: string }) => { recordAnswer(entity) }

const skipStep = () => { stepIndex.value += 1 }
const jumpTo = (index: number) => { stepIndex.value = index }

const restart = () => {
  stepIndex.value = 0
  answeredCounts.value = new Map()
}

const openBridge = (nextDomain: string) => {
  props.session.setActiveDomain(nextDomain)
  emit('exit')
}

const chipText = (index: number, entityType: string) => {
  const count = answeredCounts.value.get(index) ?? 0
  if (count === 0) return `${index + 1} ${entityType}`
  return count === 1 ? `✓ ${entityType}` : `✓ ${entityType} ×${count}`
}
</script>

<template>
  <div class="questionnaire">
    <button
      type="button"
      class="btn-link"
      @click="emit('exit')"
    >
      ← Exit questionnaire
    </button>

    <div class="step-chips">
      <button
        v-for="(step, index) in questionnaire.steps"
        :key="step.entityType"
        type="button"
        class="step-chip"
        :class="{
          'step-chip--active': index === stepIndex,
          'step-chip--answered': (answeredCounts.get(index) ?? 0) > 0,
        }"
        @click="jumpTo(index)"
      >
        {{ chipText(index, step.entityType) }}
      </button>
    </div>

    <template v-if="!complete">
      <p class="progress">
        Question {{ stepIndex + 1 }} of {{ questionnaire.steps.length }} — answer any, in any order
      </p>
      <h3 class="question">
        {{ currentStep.question }}
      </h3>
      <details
        v-if="currentTypeGuidance"
        class="type-guidance"
      >
        <summary>When to use {{ withArticle(currentStep.entityType) }}</summary>
        <!-- Broader-level context (e.g. the domain's framing) from the guidance `context`
             array, broadest first, labelled by level and shown once per view. -->
        <p
          v-for="layer in wizardContextLayers"
          :key="layer.node"
          class="type-guidance__context"
        >
          <span class="type-guidance__level">{{ contextLevelLabel(layer) }}:</span> {{ layer.text }}
        </p>
        <p v-if="currentTypeGuidance.create_when">
          {{ currentTypeGuidance.create_when }}
        </p>
        <p
          v-if="currentTypeGuidance.never_create_when"
          class="type-guidance__never"
        >
          {{ currentTypeGuidance.never_create_when }}
        </p>
      </details>
      <button
        type="button"
        class="btn-link"
        @click="skipStep"
      >
        Skip — I don't need {{ withArticle(currentStep.entityType) }} here →
      </button>
      <WizardEntityStage
        :key="currentStep.entityType"
        :entity-type="currentStep.entityType"
        :domain="questionnaire.domain"
        :guidance="guidance"
        :session="session"
        :proximity-anchors="spineAnchors"
        :name-hint="currentStep.nameHint"
        :chain-preference="currentStep.chainPreference ? [...currentStep.chainPreference] : undefined"
        allow-another
        :done-label="isLastStep ? 'Finish questionnaire' : 'Next question →'"
        @done="onStepDone"
        @another="onStepAnother"
      />
    </template>

    <template v-else>
      <h3 class="question">
        Questionnaire complete
      </h3>
      <div
        v-for="bridge in questionnaire.bridges"
        :key="bridge.nextDomain"
        class="bridge"
      >
        <p class="bridge-prompt">
          {{ bridge.prompt }}
        </p>
        <button
          type="button"
          class="btn-primary"
          @click="openBridge(bridge.nextDomain)"
        >
          {{ bridge.label }} → {{ bridge.nextDomain }}
        </button>
      </div>
      <button
        type="button"
        class="btn-link"
        @click="restart"
      >
        Start over
      </button>
    </template>
  </div>
</template>

<style scoped>
.questionnaire { display: flex; flex-direction: column; gap: 12px; }
.step-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.step-chip {
  padding: 3px 10px; border-radius: 12px; border: 1px solid #d1d5db; background: #fff;
  font-size: 12px; color: #4b5563; cursor: pointer;
}
.step-chip--active { border-color: #2563eb; color: #1d4ed8; background: #eff6ff; font-weight: 600; }
.step-chip--answered { border-color: #86efac; background: #f0fdf4; color: #15803d; }
.progress { font-size: 12px; color: #6b7280; margin: 0; text-transform: uppercase; letter-spacing: .04em; }
.question { font-size: 16px; font-weight: 600; margin: 0; color: #1f2937; }
.type-guidance { font-size: 12px; color: #4b5563; border: 1px solid #e5e7eb; border-radius: 6px; padding: 6px 10px; }
.type-guidance summary { cursor: pointer; color: #2563eb; font-weight: 600; }
.type-guidance p { margin: 6px 0 0; line-height: 1.5; }
.type-guidance__never { color: #b45309; }
.type-guidance__context { color: #6b7280; }
.type-guidance__level { font-weight: 600; text-transform: capitalize; color: #374151; }
.bridge { display: flex; flex-direction: column; gap: 6px; border-top: 1px solid #f3f4f6; padding-top: 10px; }
.bridge-prompt { font-size: 13px; color: #374151; line-height: 1.5; margin: 0; }
.btn-primary {
  align-self: flex-start; padding: 7px 16px; border-radius: 6px; border: none; background: #2563eb;
  color: #fff; font-size: 13px; font-weight: 600; cursor: pointer;
}
.btn-link { align-self: flex-start; background: none; border: none; color: #2563eb; cursor: pointer; padding: 0; font-size: 12px; text-decoration: underline; }
</style>
