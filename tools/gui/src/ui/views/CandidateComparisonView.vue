<script setup lang="ts">
/**
 * Candidate architectures compared: two or more read against one common base — the model, or a
 * candidate all of them stack on — each with its operations and its picture, side by side on a wide
 * screen and one at a time behind tabs on a narrow one. Where their operations overlap is the
 * server's integration check, asked on request. The comparison is its address: the candidates
 * (`candidate`, repeated) and the base are its operands, the diagram is how it is drawn.
 */
import { computed, inject, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Effect } from 'effect'
import type { DiagramSummary } from '../../domain'
import { comparedIds } from '../../domain/candidates/candidateComparison'
import { modelServiceKey } from '../keys'
import { candidateListRoute } from '../router/artifactRoutes'
import { useCandidateComparison } from '../composables/useCandidateComparison'
import ComparedCandidate from '../components/candidates/ComparedCandidate.vue'
import CandidateOverlaps from '../components/candidates/CandidateOverlaps.vue'

const svc = inject(modelServiceKey)!
const route = useRoute()
const router = useRouter()
const queried = (value: unknown): readonly unknown[] => (Array.isArray(value) ? value : [value])
const ids = computed(() => comparedIds(queried(route.query.candidate)))
const askedBase = computed(() => (typeof route.query.base === 'string' ? route.query.base : ''))
const diagramId = computed(() => (typeof route.query.diagram === 'string' ? route.query.diagram : ''))
const comparison = useCandidateComparison(svc, {
  ids: () => ids.value, base: () => askedBase.value, diagram: () => diagramId.value,
})

const diagrams = shallowRef<readonly DiagramSummary[]>([])
const loaded = ref(false)
const unknown = computed(() => (loaded.value ? ids.value.filter((id) => !comparison.known.value.includes(id)) : []))
const addable = computed(() => comparison.all.value.filter((one) => !ids.value.includes(one.id)))
/** Which pane a narrow screen shows; a wide one shows them all. */
const shown = ref('')
const showing = computed(() => (comparison.known.value.includes(shown.value) ? shown.value : comparison.known.value[0]))

const address = (change: Readonly<Record<string, string | string[]>>) => {
  const query = { ...route.query, ...change }
  void router.replace({
    query: Object.fromEntries(Object.entries(query).filter(([, value]) => value !== null && value !== '')),
  })
}
const add = (id: string) => {
  if (id) address({ candidate: [...ids.value, id] })
}
const drop = (id: string) => address({ candidate: ids.value.filter((one) => one !== id) })

watch(() => [comparison.known.value.join('\n'), comparison.base.value, diagramId.value], () => {
  if (loaded.value) void comparison.read()
})
onMounted(async () => {
  const [listed] = await Promise.all([
    Effect.runPromise(svc.listDiagrams()).catch(() => null),
    comparison.load(),
  ])
  diagrams.value = (listed?.items ?? []).filter((one) => one.diagram_type.startsWith('archimate'))
  loaded.value = true
  await comparison.read()
})
</script>

<template>
  <div class="workbench page">
    <div class="page-hdr">
      <RouterLink
        class="back"
        :to="candidateListRoute()"
      >
        ← Candidate architectures
      </RouterLink>
      <h1>Compare candidate architectures</h1>
    </div>
    <div class="meta">
      <label>Against
        <select
          :value="comparison.base.value"
          data-testid="common-base"
          @change="address({ base: ($event.target as HTMLSelectElement).value })"
        >
          <option
            v-for="choice in comparison.choices.value"
            :key="choice.value"
            :value="choice.value"
          >{{ choice.label }}</option>
        </select>
      </label>
      <label>Drawn on
        <select
          :value="diagramId"
          data-testid="draw-on"
          @change="address({ diagram: ($event.target as HTMLSelectElement).value })"
        >
          <option value="">no diagram</option>
          <option
            v-for="one in diagrams"
            :key="one.artifact_id"
            :value="one.artifact_id"
          >{{ one.name }}</option>
        </select>
      </label>
      <label>Add
        <select
          value=""
          data-testid="add-compared"
          @change="add(($event.target as HTMLSelectElement).value)"
        >
          <option value="">a candidate…</option>
          <option
            v-for="one in addable"
            :key="one.id"
            :value="one.id"
          >{{ one.name }}</option>
        </select>
      </label>
    </div>
    <p
      v-for="id in unknown"
      :key="id"
      class="err"
      role="alert"
    >
      No candidate architecture {{ id }}.
    </p>
    <p
      v-if="comparison.error.value"
      class="err"
      role="alert"
    >
      {{ comparison.error.value }}
    </p>
    <p
      v-if="loaded && comparison.known.value.length < 2"
      class="hint"
    >
      Add another candidate to compare it with.
    </p>
    <section
      class="card overlaps"
      aria-label="Overlaps"
    >
      <div class="ov-h">
        <span>Where their operations overlap — the same element, field or relation touched by more than one, or
          one removing what another uses. Only candidates offered for integration are checked.</span>
        <button
          type="button"
          class="btn btn-sm"
          data-testid="check-overlaps"
          :disabled="comparison.known.value.length < 2 || comparison.checking.value"
          @click="comparison.runCheck"
        >
          Check for overlaps
        </button>
      </div>
      <CandidateOverlaps
        v-if="comparison.check.value"
        :check="comparison.check.value"
        :name-of="(id) => id"
        :name-of-set="comparison.nameOf"
        none-text="No overlaps between the compared candidates."
      />
      <p
        v-if="comparison.checkError.value"
        class="err"
        role="alert"
      >
        {{ comparison.checkError.value }}
      </p>
    </section>
    <div
      class="tabs"
      role="tablist"
    >
      <button
        v-for="pane in comparison.panes.value"
        :key="pane.id"
        type="button"
        class="tab"
        role="tab"
        :aria-selected="pane.id === showing"
        @click="shown = pane.id"
      >
        {{ comparison.nameOf(pane.id) }}
      </button>
    </div>
    <div
      class="side-by-side"
      :style="{ '--panes': Math.max(comparison.panes.value.length, 1) }"
    >
      <ComparedCandidate
        v-for="pane in comparison.panes.value"
        :id="pane.id"
        :key="pane.id"
        :class="{ behind: pane.id !== showing }"
        :reading="pane.reading"
        :diagram-id="diagramId"
        :others="comparison.others.value.get(pane.id) ?? new Map()"
        :name-of-set="comparison.nameOf"
        @remove="drop"
      />
    </div>
    <p class="legend">
      + added · ~ changed — a field differs · − removed, drawn as a faded dashed ghost · each against the common base
    </p>
  </div>
</template>

<style scoped>
.page { padding: 16px 24px; }
.page-hdr { display: flex; gap: 10px; align-items: center; }
.page-hdr h1 { flex: 1; font-size: 20px; margin: 0; }
.back { color: var(--muted); text-decoration: none; font-size: 13px; }
.meta {
  display: flex; gap: 14px; flex-wrap: wrap; align-items: center; margin: 8px 0; font-size: 12px; color: var(--muted);
}
.meta select { font: inherit; margin-left: 4px; max-width: 280px; }
.err { color: var(--danger-strong); font-size: 12.5px; }
.hint { color: var(--muted); font-size: 12.5px; }
.overlaps { padding: 8px 10px; margin-bottom: 12px; font-size: 12.5px; }
.ov-h { display: flex; gap: 12px; align-items: flex-start; justify-content: space-between; color: var(--text-2); }
.side-by-side {
  display: grid; grid-template-columns: repeat(var(--panes), minmax(0, 1fr)); gap: 12px; align-items: start;
}
.page > .tabs { display: none; margin-bottom: 8px; }
.legend { font-size: 11.5px; color: var(--text-2); margin: 6px 2px; }
@media (max-width: 1100px) {
  .page > .tabs { display: flex; }
  .side-by-side { grid-template-columns: minmax(0, 1fr); }
  .behind { display: none; }
}
</style>
<style src="../components/candidates/workbench.css"></style>
