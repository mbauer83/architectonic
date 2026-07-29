<script setup lang="ts">
/**
 * The assurance projections on offer, grouped by the analysis each belongs to.
 *
 * Grouped rather than flat, because a derived diagram belongs to a unit of work: with three
 * analyses open a flat grid repeats the same four type labels nine times and never says which
 * analysis any card is for. The analysis is the heading; the type is the card.
 *
 * Choosing one opens it on its own page, so the list stays a list: no diagram renders here, and
 * arriving at this page never triggers a store read beyond the catalog itself.
 */
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  diagramDetailRoute,
  fetchAssuranceDiagrams,
  groupByAnalysis,
  type AssuranceDiagramMeta,
} from '../lib/assuranceDiagrams'

const diagrams = ref<AssuranceDiagramMeta[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const groups = computed(() => groupByAnalysis(diagrams.value))

onMounted(async () => {
  const catalog = await fetchAssuranceDiagrams()
  diagrams.value = catalog.diagrams
  error.value = catalog.error
  loading.value = false
})
</script>

<template>
  <div class="diagrams-view">
    <div class="diagrams-header">
      <RouterLink
        to="/assurance"
        class="back-link"
      >
        ← Assurance
      </RouterLink>
      <h1 class="diagrams-title">
        Assurance Diagrams
      </h1>
      <p class="diagrams-subtitle">
        Live projections from the assurance store, one set per analysis. Ephemeral — never persisted.
      </p>
    </div>

    <div
      v-if="loading"
      class="state-msg"
    >
      Loading…
    </div>
    <div
      v-else-if="error"
      class="state-error"
    >
      {{ error }}
    </div>
    <p
      v-else-if="groups.length === 0"
      class="state-msg"
    >
      No assurance diagrams are available. A derived diagram belongs to an analysis, so create one
      first.
    </p>
    <section
      v-for="group in groups"
      v-else
      :key="group.analysisId"
      class="analysis-group"
    >
      <header class="analysis-group__header">
        <h2 class="analysis-group__name">
          {{ group.analysisName }}
        </h2>
        <span class="analysis-group__method">{{ group.method }}</span>
        <span class="analysis-group__id mono">{{ group.analysisId }}</span>
      </header>
      <div class="diagram-grid">
        <RouterLink
          v-for="diagram in group.diagrams"
          :key="diagram.diagram_id"
          :to="diagramDetailRoute(diagram.analysis_id, diagram.diagram_type)"
          class="diagram-card"
        >
          <span class="diagram-card__title">{{ diagram.type_label }}</span>
          <span class="diagram-card__desc">{{ diagram.description }}</span>
        </RouterLink>
      </div>
    </section>
  </div>
</template>

<style scoped>
.diagrams-view { max-width: 1100px; margin: 0 auto; padding: 32px 24px; }
.back-link { font-size: 13px; color: #64748b; display: block; margin-bottom: 16px; }
.diagrams-title { font-size: 22px; font-weight: 700; margin: 0 0 6px; }
.diagrams-subtitle { color: #64748b; font-size: 14px; margin: 0 0 28px; }
.state-msg { color: #64748b; font-size: 14px; }
.state-error { color: #dc2626; font-size: 14px; }

.analysis-group { margin-bottom: 28px; }
.analysis-group__header { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px; }
.analysis-group__name { font-size: 15px; font-weight: 700; margin: 0; color: #111827; }
.analysis-group__method {
  font-size: 11px; font-weight: 600; color: #1d4ed8;
  background: #eff6ff; border-radius: 4px; padding: 1px 6px;
}
.analysis-group__id { font-size: 11px; color: #9ca3af; }

.diagram-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.diagram-card {
  display: flex; flex-direction: column; gap: 6px;
  padding: 16px;
  border: 1px solid #e2e8f0; border-radius: 8px;
  background: #fff; color: inherit; text-decoration: none;
}
.diagram-card:hover { border-color: #2563eb; box-shadow: 0 2px 8px rgba(0, 0, 0, .08); text-decoration: none; }
.diagram-card__title { font-size: 14px; font-weight: 600; color: #111827; }
.diagram-card__desc { font-size: 12px; color: #64748b; line-height: 1.4; }
.mono { font-family: monospace; }
</style>
