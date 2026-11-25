<script setup lang="ts">
/**
 * The one step of starting an analysis (owner, 2026-11-25): the architecture under evaluation, which
 * becomes the naive candidate. From the current model it is a scope — chosen by a diagram (the whole of
 * it or the elements pressed on the canvas), a viewpoint or a search — read live; from an existing
 * candidate it stacks on that candidate; empty, it is a blank canvas. The scope belongs to the naive
 * candidate, so there is no scope apart from it.
 */
import type { DiagramSummary, ViewpointDefinitionEnvelope } from '../../../domain'
import type { CandidateSummary } from '../../../domain/schemas/candidates'
import type { AnalysisScope } from '../../composables/useAnalysisScope'

type Origin = 'model' | 'existing' | 'empty'

defineProps<{
  scope: AnalysisScope
  diagrams: readonly DiagramSummary[]
  viewpoints: readonly ViewpointDefinitionEnvelope[]
  candidates: readonly CandidateSummary[]
}>()
const origin = defineModel<Origin>('origin', { required: true })
const fromCandidate = defineModel<string>('fromCandidate', { required: true })
const naiveName = defineModel<string>('naiveName', { required: true })

const SOURCES = { diagram: 'Diagram selection', viewpoint: 'Viewpoint', search: 'Search' } as const
const diagramName = (diagrams: readonly DiagramSummary[], id: string): string =>
  diagrams.find((one) => one.artifact_id === id)?.name ?? id
</script>

<template>
  <div
    class="step"
    data-testid="architecture-under-evaluation"
  >
    <h3>The architecture under evaluation</h3>
    <p class="lead">
      It is the <b>naive architecture</b>, the first candidate architecture of this analysis: every
      adaptation stacks on it, and nothing in it reaches the model before it is applied.
    </p>
    <label class="origin"><input
      v-model="origin"
      type="radio"
      value="model"
    ><span><b>From the current model, within a scope</b> <small>recommended</small>
      <small>Read live from the model; it starts with no operations, and what you change becomes them.</small>
    </span></label>
    <div
      v-if="origin === 'model'"
      class="scope"
    >
      <div
        class="seg"
        role="tablist"
        aria-label="Choose the scope by"
      >
        <button
          v-for="(label, one) in SOURCES"
          :key="one"
          type="button"
          role="tab"
          class="tab"
          :aria-selected="scope.source.value === one"
          @click="scope.choose.source(one)"
        >
          {{ label }}
        </button>
      </div>
      <template v-if="scope.source.value === 'diagram'">
        <label class="fld">Diagram
          <select
            :value="scope.diagramId.value"
            data-testid="scope-diagram"
            @change="scope.choose.diagram(($event.target as HTMLSelectElement).value)"
          >
            <option value="">choose…</option>
            <option
              v-for="one in diagrams"
              :key="one.artifact_id"
              :value="one.artifact_id"
            >{{ one.name }}</option>
          </select>
        </label>
        <div class="row">
          <label><input
            type="radio"
            name="scope-whole"
            :checked="scope.wholeDiagram.value"
            @change="scope.choose.whole(true)"
          > the whole diagram</label>
          <label><input
            type="radio"
            name="scope-whole"
            :checked="!scope.wholeDiagram.value"
            @change="scope.choose.whole(false)"
          > only the elements I press on the canvas</label>
        </div>
      </template>
      <template v-else-if="scope.source.value === 'viewpoint'">
        <label class="fld">Viewpoint
          <select
            :value="scope.viewpoint.value"
            data-testid="scope-viewpoint"
            @change="scope.runViewpoint(($event.target as HTMLSelectElement).value)"
          >
            <option value="">choose…</option>
            <option
              v-for="one in viewpoints"
              :key="one.slug"
              :value="one.slug"
            >{{ one.name }}</option>
          </select>
        </label>
        <p
          v-if="scope.viewpoint.value"
          class="drawn"
          data-testid="scope-drawn-on"
        >
          {{ scope.drawnOn.value
            ? `Drawn on ${diagramName(diagrams, scope.drawnOn.value)}, a stored diagram that applies this viewpoint.`
            : 'No stored diagram applies this viewpoint: the canvas shows a view generated from the scope.' }}
        </p>
      </template>
      <form
        v-else
        class="row"
        @submit.prevent="scope.search"
      >
        <input
          :value="scope.query.value"
          placeholder="Search the model"
          aria-label="Search the model"
          data-testid="scope-search"
          @input="scope.choose.query(($event.target as HTMLInputElement).value)"
        >
        <button
          type="submit"
          class="btn btn-sm"
        >
          Search
        </button>
        <div class="search-hits">
          <label
            v-for="hit in scope.hits.value"
            :key="hit.artifact_id"
          ><input
            type="checkbox"
            :checked="scope.ticked.value.has(hit.artifact_id)"
            @change="scope.tick(hit.artifact_id)"
          > {{ hit.name }} <small>{{ hit.artifact_type }}</small></label>
        </div>
      </form>
    </div>
    <label class="origin"><input
      v-model="origin"
      type="radio"
      value="existing"
    ><span><b>From an existing candidate architecture</b>
      <small>Stacks on it: its operations are read first and stay its own.</small>
      <select
        v-if="origin === 'existing'"
        v-model="fromCandidate"
        data-testid="from-candidate"
      ><option value="">choose…</option><option
        v-for="one in candidates"
        :key="one.id"
        :value="one.id"
      >{{ one.name }} ({{ one.state }})</option></select></span></label>
    <label class="origin"><input
      v-model="origin"
      type="radio"
      value="empty"
    ><span><b>Empty</b> <small>A blank canvas: no elements, no boxes.</small></span></label>
    <label class="fld">Its name <input
      v-model="naiveName"
      data-testid="naive-name"
    ></label>
  </div>
</template>

<style scoped>
.step { border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; margin: 10px 0; }
.step h3 { font-size: 13px; margin: 0 0 4px; }
.lead { color: var(--text-2); margin: 0 0 6px; }
.fld {
  display: block;
  margin: 6px 0;
  font-size: 11px;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
}
.fld input, .fld select {
  display: block;
  width: 100%;
  margin-top: 3px;
  font: inherit;
  font-size: 13px;
  font-weight: 400;
  text-transform: none;
}
.scope { margin: 6px 0 4px 26px; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 4px; }
.seg .tab { flex: none; padding: 4px 10px; }
.row { display: flex; gap: 8px 14px; align-items: center; flex-wrap: wrap; margin: 6px 0; }
.drawn { color: var(--text-2); margin: 4px 0; }
.search-hits {
  flex-basis: 100%;
  max-height: 140px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 4px;
}
.search-hits label { display: flex; gap: 6px; padding: 2px 6px; }
.search-hits small { color: var(--muted); }
.origin {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 9px;
  margin-top: 6px;
  cursor: pointer;
}
.origin:has(input:checked) {
  border-color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 3px 0 0 var(--accent);
}
.origin small { display: block; color: var(--muted); font-size: 11.5px; }
.origin select { margin-top: 4px; font-size: 12px; }
</style>
