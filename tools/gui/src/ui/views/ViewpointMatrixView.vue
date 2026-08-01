<script setup lang="ts">
/**
 * Ephemeral viewpoint-execution matrix: read-only
 * rendering via the viewpoint's `matrix` presentation — grouped axes (one population,
 * displayed with row/column grouping) or criteria axes (two independent populations,
 * `result.matrix_axes`). Never persisted, no `ViewpointApplication`.
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Effect } from 'effect'
import { RouterLink, useRoute } from 'vue-router'
import { modelServiceKey } from '../keys'
import { useViewpointExecution } from '../composables/useViewpointExecution'
import { useViewpointParameterPrompt } from '../composables/useViewpointParameterPrompt'
import { executionTitleFor } from './ViewpointsManagementView.helpers'
import ViewpointExecutionDiagnostics from '../components/ViewpointExecutionDiagnostics.vue'
import ViewpointExecutionError from '../components/ViewpointExecutionError.vue'
import ViewpointParameterPrompt from '../components/ViewpointParameterPrompt.vue'
import { computeExecutionDiagnostics, deriveLegend, deriveScaleGradients } from '../components/ViewpointExecutionDiagnostics.helpers'
import { presentationFromMapping } from '../../domain/viewpointPresentationSerialization'
import type { AdHocExecution } from '../lib/adHocExecution'
import {
  buildMatrixCells, cellEmphasisToken, cellKey, projectionByItemId, resolveMatrixAxes,
} from './ViewpointMatrixView.helpers'
import { resolveStyleColor, styleTokenString, tokenLabel } from '../lib/viewpointStyleTokens'
import type { ViewpointDefinitionEnvelope } from '../../domain'

const props = defineProps<{ adHoc?: AdHocExecution }>()

const svc = inject(modelServiceKey)!
const route = useRoute()
const slug = computed(() => route.params.slug as string)

const definitions = ref<readonly ViewpointDefinitionEnvelope[]>([])
const execution = useViewpointExecution(svc)
const prompt = useViewpointParameterPrompt((resolved) => execution.execute(resolved), definitions)

const presentation = computed(() => {
  if (props.adHoc) return props.adHoc.presentation
  const envelope = definitions.value.find((d) => d.slug === slug.value)
  return envelope ? presentationFromMapping(envelope.presentation) : null
})
const diagnostics = computed(() => computeExecutionDiagnostics(execution.result.value, presentation.value, 'matrix'))
const legend = computed(() => deriveLegend(presentation.value, execution.projection.value?.rule_outcomes ?? []))
const scaleGradients = computed(() =>
  deriveScaleGradients(presentation.value, execution.projection.value?.scale_legends ?? []))
const entityStyleById = computed(() => projectionByItemId(execution.projection.value))
const axes = computed(() => resolveMatrixAxes(presentation.value, execution.result.value))
const cells = computed(() => buildMatrixCells(axes.value.rowIds, axes.value.columnIds, execution.result.value?.connections ?? []))
const entityNameById = computed(() => new Map((execution.result.value?.entities ?? []).map((e) => [e.id, e.name])))

const cellLabel = (rowId: string, columnId: string): string => {
  const cell = cells.value.get(cellKey(rowId, columnId))
  return cell ? `${cell.connectionCount} (${cell.connectionTypes.join(', ')})` : ''
}
const cellColor = (rowId: string, columnId: string): string | null => {
  const token = cellEmphasisToken(rowId, columnId, entityStyleById.value)
  return token !== undefined ? resolveStyleColor(token) : null
}
const cellTitle = (rowId: string, columnId: string): string | undefined => {
  const token = cellEmphasisToken(rowId, columnId, entityStyleById.value)
  return token !== undefined ? tokenLabel(styleTokenString(token)) : undefined
}

const load = async () => {
  definitions.value = await Effect.runPromise(svc.listViewpointDefinitions()).catch(() => [])
  if (props.adHoc) { await execution.execute(props.adHoc.request); return }
  await prompt.run(slug.value)
}
const rerun = () => void load()

onMounted(() => { if (props.adHoc || slug.value) void load() })
</script>

<template>
  <div class="page">
    <div class="hdr">
      <h1 class="pg-title">
        {{ executionTitleFor(slug, definitions) }} <span class="count">— matrix</span>
      </h1>
      <div class="hdr-actions">
        <RouterLink
          v-if="!adHoc && slug"
          :to="{ path: '/viewpoints/query', query: { slug } }"
          class="view-as-link"
          title="Re-present this saved viewpoint with a different presentation, without changing it"
        >
          View as… (unsaved)
        </RouterLink>
        <RouterLink
          to="/viewpoints"
          class="back-link"
        >
          ← Viewpoints
        </RouterLink>
      </div>
    </div>

    <ViewpointExecutionDiagnostics
      v-if="!prompt.visible.value && !execution.errorMessage.value"
      :diagnostics="diagnostics"
      :legend="legend"
      :scale-gradients="scaleGradients"
      :query-summary="execution.result.value?.query_summary ?? ''"
      @rerun="rerun"
    />

    <ViewpointParameterPrompt
      v-if="prompt.visible.value"
      :parameters="prompt.parameters.value"
      @submit="prompt.submit"
      @cancel="prompt.cancel"
    />

    <div
      v-if="execution.loading.value"
      class="state-msg"
    >
      Loading…
    </div>
    <ViewpointExecutionError
      v-else-if="execution.errorMessage.value"
      :typed-error="execution.typedError.value"
      :fallback-message="execution.errorMessage.value"
      @retry="rerun"
    />
    <div
      v-else-if="axes.rowIds.length > 0 && axes.columnIds.length > 0"
      class="matrix-scroll"
    >
      <table class="matrix-table">
        <thead>
          <tr>
            <th />
            <th
              v-for="columnId in axes.columnIds"
              :key="columnId"
            >
              {{ entityNameById.get(columnId) ?? columnId }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="rowId in axes.rowIds"
            :key="rowId"
          >
            <th>{{ entityNameById.get(rowId) ?? rowId }}</th>
            <td
              v-for="columnId in axes.columnIds"
              :key="columnId"
              :style="cellColor(rowId, columnId) ? { background: cellColor(rowId, columnId) as string } : {}"
              :title="cellTitle(rowId, columnId)"
            >
              {{ cellLabel(rowId, columnId) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; padding: 24px 16px; }
.hdr { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.pg-title { font-size: 20px; font-weight: 600; margin: 0; }
.count { color: #6b7280; font-weight: 400; font-size: 14px; }
.hdr-actions { display: flex; align-items: center; gap: 14px; }
.back-link { font-size: 13px; color: #6b7280; text-decoration: none; }
.back-link:hover { color: #374151; }
.view-as-link { font-size: 13px; color: #4338ca; text-decoration: none; border: 1px solid #c7d2fe; border-radius: 6px; padding: 4px 10px; }
.view-as-link:hover { background: #eef2ff; }
.state-msg { color: #9ca3af; font-size: 14px; padding: 24px 0; }
.state-msg--error { color: #dc2626; }
.matrix-scroll { overflow: auto; max-height: clamp(300px, 65vh, 800px); border: 1px solid #e5e7eb; border-radius: 8px; }
.matrix-table { border-collapse: collapse; font-size: 12px; }
.matrix-table th, .matrix-table td { border: 1px solid #e5e7eb; padding: 6px 8px; text-align: center; white-space: nowrap; }
.matrix-table thead th { position: sticky; top: 0; background: #f9fafb; z-index: 1; }
.matrix-table tbody th { position: sticky; left: 0; background: #f9fafb; text-align: left; z-index: 1; }
</style>
