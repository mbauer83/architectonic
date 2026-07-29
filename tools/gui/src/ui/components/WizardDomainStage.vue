<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { useWizardSession } from '../composables/useWizardSession'
import type { AuthoringGuidance } from '../../domain'
import WizardEntityStage from './WizardEntityStage.vue'
import WizardQuestionnaireStage from './WizardQuestionnaireStage.vue'
import { entityTypesForDomain, splitVisibleEntityTypes } from './WizardDomainStage.helpers'
import { questionnaireForDomain } from '../lib/wizardQuestionnaires'

const props = defineProps<{
  domain: string
  guidance: AuthoringGuidance | null
  session: ReturnType<typeof useWizardSession>
}>()

const entityTypes = computed(() => entityTypesForDomain(props.guidance, props.domain))
const questionnaire = computed(() => questionnaireForDomain(props.domain))
const typeSplit = computed(() => splitVisibleEntityTypes(
  entityTypes.value, 4, questionnaire.value?.steps.map((s) => s.entityType) ?? []))
const showAllTypes = ref(false)
const questionnaireStarted = ref(false)

const chosenType = ref<string | null>(null)

/** Full guidance for the native tooltip — the clamped hint expands nowhere, so hover reveals
 * the rest without reflowing the grid. */
const typeTooltip = (t: { create_when: string; never_create_when: string }) =>
  [t.create_when, t.never_create_when && `Never: ${t.never_create_when}`]
    .filter(Boolean).join('\n\n')

const chooseType = (type: string) => { chosenType.value = type }
const resetToTypeChoice = () => { chosenType.value = null }

watch(() => props.domain, () => { resetToTypeChoice(); questionnaireStarted.value = false })
</script>

<template>
  <div class="wizard-stage">
    <WizardQuestionnaireStage
      v-if="questionnaireStarted && questionnaire"
      :questionnaire="questionnaire"
      :guidance="guidance"
      :session="session"
      @exit="questionnaireStarted = false"
    />

    <div
      v-else-if="!chosenType"
      class="type-choice"
    >
      <button
        v-if="questionnaire"
        type="button"
        class="questionnaire-cta"
        @click="questionnaireStarted = true"
      >
        ✨ Start the guided {{ domain }} questionnaire — {{ questionnaire.steps.length }} short
        questions from {{ questionnaire.steps[0].entityType }} to
        {{ questionnaire.steps[questionnaire.steps.length - 1].entityType }}. Answer any,
        in any order — every question is skippable.
      </button>

      <p class="stage-hint">
        Or pick a type directly:
      </p>
      <p
        v-if="guidance?.guidance_status === 'empty'"
        class="guidance-empty-hint"
      >
        {{ guidance.guidance_hint }}
      </p>
      <div class="type-grid">
        <button
          v-for="t in (showAllTypes ? [...typeSplit.visible, ...typeSplit.rest] : typeSplit.visible)"
          :key="t.name"
          type="button"
          class="type-btn"
          :title="typeTooltip(t)"
          @click="chooseType(t.name)"
        >
          <span class="type-name">New {{ t.name }}</span>
          <span
            v-if="t.create_when"
            class="type-hint"
          >{{ t.create_when }}</span>
        </button>
      </div>
      <button
        v-if="!showAllTypes && typeSplit.rest.length > 0"
        type="button"
        class="btn-link"
        @click="showAllTypes = true"
      >
        + Show all {{ entityTypes.length }} types
      </button>
    </div>

    <div
      v-else
      class="stage-body"
    >
      <button
        type="button"
        class="btn-link"
        @click="resetToTypeChoice"
      >
        ← Choose a different type
      </button>
      <WizardEntityStage
        :entity-type="chosenType"
        :domain="domain"
        :guidance="guidance"
        :session="session"
        allow-another
        done-label="Done — choose another type"
        @done="resetToTypeChoice"
      />
    </div>
  </div>
</template>

<style scoped>
.wizard-stage { display: flex; flex-direction: column; gap: 14px; }
.questionnaire-cta {
  text-align: left; padding: 12px 16px; border: 1px solid #bfdbfe; border-radius: 8px;
  background: #eff6ff; color: #1d4ed8; font-size: 13px; font-weight: 600; cursor: pointer;
}
.questionnaire-cta:hover { background: #dbeafe; }
.stage-hint { color: #4b5563; font-size: 13px; margin: 0; }
.guidance-empty-hint {
  font-size: 12px; color: #92400e; background: #fffbeb; border: 1px solid #fde68a;
  border-radius: 6px; padding: 8px 10px; margin: 0;
}
.type-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.type-btn {
  display: flex; flex-direction: column; gap: 3px; text-align: left; padding: 10px 12px;
  border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; cursor: pointer;
}
.type-btn:hover { border-color: #93c5fd; }
.type-name { font-weight: 600; font-size: 13px; }
/* Fixed clamp with the full text in the button's title attribute — expanding in place on hover
 * would reflow the whole grid under the cursor. */
.type-hint {
  font-size: 12px; color: #6b7280;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden;
}
.btn-link { align-self: flex-start; background: none; border: none; color: #2563eb; cursor: pointer; padding: 0; font-size: 12px; text-decoration: underline; }
.stage-body { display: flex; flex-direction: column; gap: 14px; }
</style>
