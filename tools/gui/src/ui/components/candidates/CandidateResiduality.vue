<script setup lang="ts">
/**
 * A candidate's residuality in each stress analysis that judged it against its test set, one quiet
 * line each with a link to the analysis. Nothing shows for a candidate no analysis has judged, and a
 * read that fails shows nothing either: the figure is a reading aid on this page, not its subject.
 */
import { inject, shallowRef, watch } from 'vue'
import { Effect } from 'effect'
import type { AnalysisStanding } from '../../../domain/schemas/stressEvaluation'
import { modelServiceKey } from '../../keys'
import { stressAnalysisWorkspaceRoute } from '../../router/artifactRoutes'
import ResidualityLine from './ResidualityLine.vue'

const props = defineProps<{ candidateId: string }>()
const svc = inject(modelServiceKey)!
const analyses = shallowRef<readonly AnalysisStanding[]>([])

watch(() => props.candidateId, async (id) => {
  analyses.value = []
  const read = await Effect.runPromise(svc.readResiduality(id)).catch(() => null)
  if (read?.candidate === props.candidateId) analyses.value = read.analyses
}, { immediate: true })
</script>

<template>
  <div
    v-if="analyses.length"
    class="by-analysis"
  >
    <ResidualityLine
      v-for="one in analyses"
      :key="one.document"
      :standing="one"
    >
      <template #who>
        <RouterLink
          class="analysis"
          :to="stressAnalysisWorkspaceRoute(one.document)"
          title="The stress analysis whose test set judged it"
        >
          {{ one.title }}
        </RouterLink>
      </template>
    </ResidualityLine>
  </div>
</template>

<style scoped>
.by-analysis { display: grid; gap: 2px; margin: 2px 0 6px; }
.analysis { color: var(--accent-strong); text-decoration: none; font-size: 12px; }
.analysis:hover { text-decoration: underline; }
</style>
