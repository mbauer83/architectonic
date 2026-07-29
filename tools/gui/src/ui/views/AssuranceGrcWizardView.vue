<script setup lang="ts">
import { ref, onMounted, provide, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AssuranceAnalysisPicker from '../components/AssuranceAnalysisPicker.vue'
import GrcRisksStep from '../components/GrcRisksStep.vue'
import GrcTreatmentStep from '../components/GrcTreatmentStep.vue'
import GrcControlsStep from '../components/GrcControlsStep.vue'
import GrcObligationsStep from '../components/GrcObligationsStep.vue'
import GrcCoverageStep from '../components/GrcCoverageStep.vue'
import { grcWizardDataKey, useGrcWizardData } from '../composables/useGrcWizardData'
import { GRC_STEPS } from './AssuranceGrcWizard.helpers'

const route = useRoute()
const router = useRouter()

const analysisId = ref<string | null>(
  typeof route.query['analysis_id'] === 'string' ? route.query['analysis_id'] : null,
)
const stepKey = ref<string>('risks')

const data = useGrcWizardData(analysisId, stepKey)
provide(grcWizardDataKey, data)

function goToStep(key: string) {
  stepKey.value = key
}

watch(analysisId, (val) => {
  void router.replace({ path: '/assurance/grc', query: val ? { analysis_id: val } : {} })
})

onMounted(() => {
  void data.loadNodes()
  void data.loadGuidance()
  void data.loadCompleteness()
})
</script>

<template>
  <div class="wiz">
    <div class="wiz-header">
      <h1 class="wiz-title">
        GRC wizard
      </h1>
      <AssuranceAnalysisPicker
        v-model="analysisId"
        default-method="GRC"
      />
    </div>

    <div
      v-if="data.error"
      class="wiz-error"
    >
      {{ data.error }}
    </div>

    <p
      v-if="!analysisId"
      class="wiz-hint"
    >
      Select or create a GRC analysis above to begin. Every risk, control and
      obligation you author belongs to that analysis.
    </p>

    <template v-else>
      <!-- Stepper -->
      <nav class="stepper">
        <button
          v-for="(s, i) in GRC_STEPS"
          :key="s.key"
          class="step-tab"
          :class="{ 'step-tab--active': s.key === stepKey, 'step-tab--done': data.contentSteps.has(s.key) }"
          type="button"
          @click="goToStep(s.key)"
        >
          <span class="step-num">{{ i + 1 }}</span>
          {{ s.label }}
        </button>
      </nav>

      <!-- Guidance -->
      <div
        v-if="data.guidance.what"
        class="guidance"
      >
        <p class="guidance-what">
          {{ data.guidance.what }}
        </p>
        <p
          v-if="data.guidance.why"
          class="guidance-why"
        >
          {{ data.guidance.why }}
        </p>
        <p
          v-if="data.guidance.how"
          class="guidance-how"
        >
          {{ data.guidance.how }}
        </p>
      </div>

      <GrcRisksStep v-if="data.currentStep.key === 'risks'" />
      <GrcTreatmentStep v-else-if="data.currentStep.key === 'treatment'" />
      <GrcControlsStep v-else-if="data.currentStep.key === 'controls'" />
      <GrcObligationsStep v-else-if="data.currentStep.key === 'obligations'" />
      <GrcCoverageStep v-else />
    </template>
  </div>
</template>

<style scoped>
.wiz { padding: 20px 24px; max-width: 900px; }
.wiz-header { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
.wiz-title { font-size: 20px; font-weight: 700; margin: 0; }
.wiz-error { padding: 10px 14px; background: #fef2f2; color: #b91c1c; border-radius: 6px; margin-bottom: 12px; font-size: 13px; }
.wiz-hint { color: #64748b; font-size: 14px; }
.stepper { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }
.step-tab {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px; border: 1px solid #e2e8f0; border-radius: 6px;
  background: #fff; color: #475569; font-size: 13px; cursor: pointer;
}
.step-tab--active { background: #2563eb; color: #fff; border-color: #2563eb; }
.step-tab--done:not(.step-tab--active) { border-color: #86efac; }
.step-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 50%; background: #e2e8f0; color: #475569; font-size: 11px;
}
.step-tab--active .step-num { background: rgba(255,255,255,0.3); color: #fff; }
.guidance { background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; }
.guidance-what { font-size: 14px; font-weight: 600; color: #075985; margin: 0 0 4px; }
.guidance-why { font-size: 13px; color: #0c4a6e; margin: 0 0 4px; }
.guidance-how { font-size: 12px; color: #0369a1; margin: 0; }
</style>
