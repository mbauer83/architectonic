<script setup lang="ts">
import { computed, inject, onMounted, ref } from 'vue'
import { Effect } from 'effect'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import type { ViewpointDefinitionEnvelope } from '../../domain'
import { modelServiceKey } from '../keys'
import { useViewpointExecution } from '../composables/useViewpointExecution'
import { useViewpointParameterPrompt } from '../composables/useViewpointParameterPrompt'
import type { ResolvedViewpointExecution } from '../composables/useViewpointParameterPrompt'
import { parameterSignatureOf } from '../lib/viewpointExecutionParameters'
import { executionQuery, parametersFromQuery } from '../lib/viewpointUrlState'
import ViewpointExecutionDiagnostics from './ViewpointExecutionDiagnostics.vue'
import ViewpointExecutionError from './ViewpointExecutionError.vue'
import ViewpointExecutionToolbar from './ViewpointExecutionToolbar.vue'
import ViewpointParameterPrompt from './ViewpointParameterPrompt.vue'
import ViewpointTableCell from './ViewpointTableCell.vue'
import ViewpointTraceTable from './ViewpointTraceTable.vue'
import { computeExecutionDiagnostics, deriveLegend, deriveScaleGradients } from './ViewpointExecutionDiagnostics.helpers'
import { executionTitleFor } from '../views/ViewpointsManagementView.helpers'
import { presentationFromMapping } from '../../domain/viewpointPresentationSerialization'
import type { AdHocExecution } from '../lib/adHocExecution'
import {
  effectiveTableColumns, groupTableRows, hasBadgeStyling,
  projectionByItemId, sortEntitiesBy, type SortDirection,
} from '../views/EntitiesView.helpers'

/** Table representation of a viewpoint execution: the entity catalog driven by a fixed
 * viewpoint population — authored columns, group_by sections, click-to-sort, badge
 * styling, and a server-generated complete CSV export. */
const props = defineProps<{ slug: string; adHoc?: AdHocExecution }>()

const svc = inject(modelServiceKey)!
const route = useRoute()
const router = useRouter()
const viewpointDefinitions = ref<readonly ViewpointDefinitionEnvelope[]>([])
const viewpointExecution = useViewpointExecution(svc)
const lastResolvedExecution = ref<ResolvedViewpointExecution | null>(null)

// One path for every execution (prompt, toolbar Apply, or a URL-seeded first run): record
// what ran, snapshot it into the URL (replace, so the back button isn't polluted) so the
// link reproduces the exact selection, then execute.
const runResolved = (resolved: ResolvedViewpointExecution) => {
  lastResolvedExecution.value = resolved
  void router.replace({ query: executionQuery(resolved.slug, resolved.parameters) })
  return viewpointExecution.execute(resolved)
}
const viewpointPrompt = useViewpointParameterPrompt(runResolved, viewpointDefinitions)

const viewpointParameterSignature = computed(() =>
  parameterSignatureOf(viewpointDefinitions.value.find((d) => d.slug === props.slug)))
const toolbarBoundValues = computed(() => lastResolvedExecution.value?.parameters ?? {})
const applyParameters = (parameters: Record<string, unknown>) =>
  runResolved({ slug: props.slug, parameters })

const selectedViewpointPresentation = computed(() => {
  if (props.adHoc) return props.adHoc.presentation
  const envelope = viewpointDefinitions.value.find((d) => d.slug === props.slug)
  return envelope ? presentationFromMapping(envelope.presentation) : null
})
const viewpointDiagnostics = computed(() => computeExecutionDiagnostics(
  viewpointExecution.result.value, selectedViewpointPresentation.value, 'table',
))
const viewpointLegend = computed(() =>
  deriveLegend(selectedViewpointPresentation.value, viewpointExecution.projection.value?.rule_outcomes ?? []))
const viewpointScaleGradients = computed(() =>
  deriveScaleGradients(selectedViewpointPresentation.value, viewpointExecution.projection.value?.scale_legends ?? []))
const viewpointEntityStyleById = computed(() => projectionByItemId(viewpointExecution.projection.value))
const viewpointColumns = computed(() => effectiveTableColumns(selectedViewpointPresentation.value?.columns ?? null))
const showStyleColumn = computed(() => hasBadgeStyling(selectedViewpointPresentation.value))
const sortSource = ref<string | null>(null)
const sortDirection = ref<SortDirection>('asc')
const toggleSort = (source: string) => {
  if (sortSource.value === source) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortSource.value = source
    sortDirection.value = 'asc'
  }
}
const viewpointRowGroups = computed(() => {
  const entities = viewpointExecution.result.value?.entities ?? []
  const sorted = sortSource.value !== null ? sortEntitiesBy(entities, sortSource.value, sortDirection.value) : entities
  return groupTableRows(sorted, selectedViewpointPresentation.value?.groupBy ?? null)
})

const exportingCsv = ref(false)
const exportCsv = () => {
  if (exportingCsv.value) return
  const resolved = lastResolvedExecution.value
  // Ad-hoc export carries the same request (inline query + presentation, or slug + override)
  // so the CSV columns follow the effective presentation, not a re-fetched saved one.
  const body = props.adHoc ? props.adHoc.request : (resolved ? { slug: resolved.slug, parameters: resolved.parameters } : null)
  if (!body) return
  const baseName = props.adHoc ? 'viewpoint-query' : (resolved?.slug ?? 'viewpoint-export')
  exportingCsv.value = true
  Effect.runPromise(svc.exportViewpointCsv(body))
    .then((text) => {
      const generation = viewpointExecution.result.value?.index_generation ?? 'live'
      const link = document.createElement('a')
      link.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
      link.download = `${baseName}-gen${generation}.csv`
      link.click()
      URL.revokeObjectURL(link.href)
    })
    .catch((error: unknown) => { console.error('CSV export failed', error) })
    .finally(() => { exportingCsv.value = false })
}

const loadViewpointTable = async () => {
  viewpointDefinitions.value = await Effect.runPromise(svc.listViewpointDefinitions()).catch(() => [])
  if (props.adHoc) { await viewpointExecution.execute(props.adHoc.request); return }
  await viewpointPrompt.run(props.slug, parametersFromQuery(route.query))
}

const rerunViewpointTable = () => { void loadViewpointTable() }

onMounted(() => { void loadViewpointTable() })
</script>

<template>
  <div class="vp-table-page">
    <div class="vp-table-header">
      <h1 class="page-title">
        {{ executionTitleFor(slug, viewpointDefinitions) }} <span class="count">— table</span>
      </h1>
      <div class="header-actions">
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

    <ViewpointExecutionToolbar
      v-if="!viewpointPrompt.visible.value && viewpointParameterSignature.length > 0"
      :parameters="viewpointParameterSignature"
      :bound-values="toolbarBoundValues"
      @apply="applyParameters"
    />
    <ViewpointExecutionDiagnostics
      v-if="!viewpointPrompt.visible.value && !viewpointExecution.errorMessage.value"
      :diagnostics="viewpointDiagnostics"
      :legend="viewpointLegend"
      :scale-gradients="viewpointScaleGradients"
      :query-summary="viewpointExecution.result.value?.query_summary ?? ''"
      @rerun="rerunViewpointTable"
    />
    <div
      v-if="viewpointExecution.result.value"
      class="export-row"
    >
      <button
        type="button"
        class="export-btn"
        :disabled="exportingCsv"
        title="Server-generated CSV of the COMPLETE result at this execution's generation, with a provenance header"
        @click="exportCsv"
      >
        {{ exportingCsv ? 'Exporting…' : '⬇ Export CSV (complete result)' }}
      </button>
    </div>

    <ViewpointParameterPrompt
      v-if="viewpointPrompt.visible.value"
      :parameters="viewpointPrompt.parameters.value"
      @submit="viewpointPrompt.submit"
      @cancel="viewpointPrompt.cancel"
    />

    <div
      v-if="viewpointExecution.loading.value"
      class="state-msg"
    >
      Loading…
    </div>
    <ViewpointExecutionError
      v-else-if="viewpointExecution.errorMessage.value"
      :typed-error="viewpointExecution.typedError.value"
      :fallback-message="viewpointExecution.errorMessage.value"
      @retry="rerunViewpointTable"
    />
    <table
      v-else-if="viewpointRowGroups.length > 0"
      class="entity-table"
    >
      <thead>
        <tr>
          <th
            v-for="col in viewpointColumns"
            :key="col.source"
            class="sortable-header"
            :aria-sort="sortSource === col.source ? (sortDirection === 'asc' ? 'ascending' : 'descending') : undefined"
            @click="toggleSort(col.source)"
          >
            {{ col.label }}
            <span
              v-if="sortSource === col.source"
              class="sort-indicator"
            >{{ sortDirection === 'asc' ? '▲' : '▼' }}</span>
          </th>
          <th v-if="showStyleColumn">
            Style
          </th>
        </tr>
      </thead>
      <tbody>
        <template
          v-for="group in viewpointRowGroups"
          :key="group.groupKey || '(all)'"
        >
          <tr
            v-if="group.groupKey"
            class="vp-group-row"
          >
            <td :colspan="viewpointColumns.length + (showStyleColumn ? 1 : 0)">
              {{ group.groupKey }}
            </td>
          </tr>
          <tr
            v-for="entity in group.entities"
            :key="entity.id"
          >
            <td
              v-for="col in viewpointColumns"
              :key="col.source"
            >
              <ViewpointTableCell
                :entity="entity"
                :source="col.source"
              />
            </td>
            <td v-if="showStyleColumn">
              <span
                v-if="viewpointEntityStyleById.get(entity.id)?.style.badges"
                class="vp-badge"
              >{{ viewpointEntityStyleById.get(entity.id)?.style.badges }}</span>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
    <ViewpointTraceTable :table="viewpointExecution.result.value?.trace_table ?? null" />
  </div>
</template>

<style scoped>
.vp-table-page { max-width: 1100px; margin: 0 auto; }
.vp-table-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.page-title { font-size: 22px; font-weight: 600; }
.count { margin-left: 6px; font-size: 14px; font-weight: 400; color: #6b7280; }
.state-msg { color: #6b7280; }
.header-actions { display: flex; align-items: center; gap: 14px; }
.back-link { font-size: 13px; color: #6b7280; text-decoration: none; }
.back-link:hover { color: #374151; }
.view-as-link { font-size: 13px; color: #4338ca; text-decoration: none; border: 1px solid #c7d2fe; border-radius: 6px; padding: 4px 10px; }
.view-as-link:hover { background: #eef2ff; }

.entity-table { width: 100%; border-collapse: collapse; background: white; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }
.entity-table th, .entity-table td { padding: 10px 14px; text-align: left; }
.entity-table th { background: #f9fafb; border-bottom: 1px solid #e5e7eb; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; }
.entity-table td { border-bottom: 1px solid #f3f4f6; font-size: 13px; }
.entity-table tr:last-child td { border-bottom: 0; }
.entity-table tr:hover td { background: #f9fafb; }

.vp-group-row td { background: #f3f4f6; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; }
.sortable-header { cursor: pointer; user-select: none; white-space: nowrap; }
.sortable-header:hover { color: #4338ca; }
.sort-indicator { font-size: 9px; margin-left: 2px; }
.export-row { margin: 6px 0; }
.export-btn {
  font-size: 12px; padding: 4px 12px; border: 1px solid #d1d5db; border-radius: 5px;
  background: white; cursor: pointer; color: #374151;
}
.export-btn:hover:not(:disabled) { background: #f9fafb; }
.export-btn:disabled { color: #9ca3af; cursor: wait; }
.vp-badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; background: #eef2ff; color: #4338ca; }
</style>
