<script setup lang="ts">
/**
 * Build an ephemeral (never saved) layered view or motivation-support view — select roots
 * by name/id or by criteria, pull in indirectly-connected neighbors of a chosen kind,
 * review derived candidates, inspect witness chains, and optionally materialize one
 * derived relationship into a real connection. Everything here executes through the
 * existing ad-hoc `query` viewpoint-execution path; nothing is persisted.
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { useForceGraph } from '../composables/useForceGraph'
import { useViewpointExecution } from '../composables/useViewpointExecution'
import { buildLayeredViewQuery } from '../../domain/layeredViewQuery'
import { queryToMapping } from '../../domain/viewpointCriteriaSerialization'
import {
  initialCandidateReview, withDecision, decisionFor, candidateKeyFor, staleAcceptedFindings, clearDecision,
  type CandidateReviewState, type StaleFinding,
} from '../../domain/derivedCandidateReview'
import { buildRenderGraph, derivedCandidates } from './LayeredExplorationView.helpers'
import { certaintyDashArray, CERTAINTY_LABELS } from '../lib/viewpointStyleTokens'
import type { CriteriaCatalog, ConnectionItemSummary, EntityItemSummary } from '../../domain'
import type { GroupNode } from '../../domain/viewpointCriteria'
import LayeredViewBuilderPanel from '../components/LayeredViewBuilderPanel.vue'
import CandidateReviewPanel from '../components/CandidateReviewPanel.vue'
import WitnessChainPopover from '../components/WitnessChainPopover.vue'
import MaterializeConnectionDialog from '../components/MaterializeConnectionDialog.vue'

const svc = inject(modelServiceKey)!
const execution = useViewpointExecution(svc)
const { nodes, edges, addNode, addEdge, applyForceLayout } = useForceGraph(() => 800, () => 600)

const catalog = ref<CriteriaCatalog | null>(null)
onMounted(() => { void Effect.runPromise(svc.getCriteriaCatalog()).then((c) => { catalog.value = c }) })

const review = ref<CandidateReviewState>(initialCandidateReview([]))
const staleFindings = ref<readonly StaleFinding[]>([])
const staleEntityNames = ref<ReadonlyMap<string, string>>(new Map())
const hasRendered = ref(false)
const explaining = ref<ConnectionItemSummary | null>(null)
const materializing = ref<ConnectionItemSummary | null>(null)
const entityById = computed(() => new Map((execution.result.value?.entities ?? []).map((e) => [e.id, e])))

const entityLabel = (id: string): string => entityById.value.get(id)?.name ?? staleEntityNames.value.get(id) ?? id

const edgeKeyOf = (source: string, target: string, type: string): string => `${source}|${target}|${type}`
const connectionByKey = computed(() =>
  new Map((execution.result.value?.connections ?? []).map((c) => [edgeKeyOf(c.source, c.target, c.type), c])),
)

const rebuildGraph = (): void => {
  nodes.value = []
  edges.value = []
  const result = execution.result.value
  if (!result) return
  const graph = buildRenderGraph(result.entities, result.connections, review.value)
  for (const n of graph.nodes) addNode({ id: n.id, label: n.label, type: n.type })
  for (const e of graph.edges) addEdge({ source: e.source, target: e.target, connType: e.connType })
  applyForceLayout()
}

interface RenderParams {
  rootEntityIds: readonly string[]
  rootCriteria: GroupNode | null
  neighborCriteria: GroupNode
  includePotential: boolean
  maxHops: number
}

const runRender = async (params: RenderParams): Promise<void> => {
  const previousConnections = execution.result.value?.connections ?? []
  const previousEntities = execution.result.value?.entities ?? []
  const previousReview = review.value
  const query = buildLayeredViewQuery(params)
  await execution.execute({ query: queryToMapping(query) })
  const result = execution.result.value
  if (!result) return
  if (hasRendered.value) {
    staleFindings.value = staleAcceptedFindings(previousReview, previousConnections, result.connections)
    staleEntityNames.value = new Map(previousEntities.map((e) => [e.id, e.name]))
  } else {
    staleFindings.value = []
  }
  review.value = initialCandidateReview(result.connections)
  hasRendered.value = true
  rebuildGraph()
}

const toggleDecision = (connection: ConnectionItemSummary): void => {
  const key = candidateKeyFor(connection)
  const next = decisionFor(review.value, key) === 'accepted' ? 'rejected' : 'accepted'
  review.value = withDecision(review.value, key, next)
  rebuildGraph()
}

/** Acknowledges one stale finding — clears its decision (so it isn't reported again on a
 * future re-run) and removes it from the list. Every other finding is untouched. */
const removeStaleFinding = (finding: StaleFinding): void => {
  review.value = clearDecision(review.value, finding.key)
  staleFindings.value = staleFindings.value.filter((f) => f.key !== finding.key)
}

/** Re-review: reopens the same witness-chain popover live candidates use, against the
 * finding's last-known connection — reconstruction may now report `broken`, which is
 * itself the informative answer to "why did this go stale". */
const reReviewStaleFinding = (finding: StaleFinding): void => { explaining.value = finding.connection }

const materializeTarget = computed(() => {
  const candidate = materializing.value
  if (!candidate) return null
  const source = entityById.value.get(candidate.source)
  const target = entityById.value.get(candidate.target)
  if (!source || !target) return null
  return { source, target }
})
</script>

<template>
  <div class="layered-view">
    <h1 class="page-title">
      Build a layered view
    </h1>
    <LayeredViewBuilderPanel
      v-if="catalog"
      :catalog="catalog"
      @render="runRender"
    />

    <div
      v-if="staleFindings.length > 0"
      class="stale-banner"
    >
      <p class="stale-banner-title">
        {{ staleFindings.length }} previously-accepted relationship{{ staleFindings.length === 1 ? '' : 's' }} no longer derive{{ staleFindings.length === 1 ? 's' : '' }} after this re-run:
      </p>
      <ul class="stale-finding-list">
        <li
          v-for="finding in staleFindings"
          :key="finding.key"
          class="stale-finding"
        >
          <span class="stale-finding-desc">{{ entityLabel(finding.connection.source) }} → {{ entityLabel(finding.connection.target) }} ({{ finding.connection.type }})</span>
          <button
            type="button"
            @click="reReviewStaleFinding(finding)"
          >
            Re-review
          </button>
          <button
            type="button"
            @click="removeStaleFinding(finding)"
          >
            Remove
          </button>
        </li>
      </ul>
    </div>

    <template v-if="hasRendered">
      <div class="legend">
        <span class="legend-entry"><span class="legend-swatch legend-swatch--certain" />{{ CERTAINTY_LABELS.certain }}</span>
        <span class="legend-entry"><span class="legend-swatch legend-swatch--potential" />{{ CERTAINTY_LABELS.potential }}</span>
      </div>

      <svg
        class="graph-svg"
        viewBox="0 0 800 600"
      >
        <g
          v-for="(e, i) in edges"
          :key="'e' + i"
          class="graph-edge"
        >
          <path
            :d="`M ${nodes.find((n) => n.id === e.source)?.x ?? 0} ${nodes.find((n) => n.id === e.source)?.y ?? 0} L ${nodes.find((n) => n.id === e.target)?.x ?? 0} ${nodes.find((n) => n.id === e.target)?.y ?? 0}`"
            stroke="#9ca3af"
            fill="none"
            :stroke-dasharray="certaintyDashArray(connectionByKey.get(edgeKeyOf(e.source, e.target, e.connType))?.certainty ?? null) ?? undefined"
            :class="{ 'derived-edge': connectionByKey.get(edgeKeyOf(e.source, e.target, e.connType))?.certainty }"
            @click="() => { const c = connectionByKey.get(edgeKeyOf(e.source, e.target, e.connType)); if (c?.certainty) explaining = c }"
          />
        </g>
        <g
          v-for="n in nodes"
          :key="n.id"
          class="graph-node"
          :transform="`translate(${n.x}, ${n.y})`"
        >
          <circle
            r="16"
            fill="#6366f1"
            opacity="0.85"
          />
          <text
            dy="30"
            text-anchor="middle"
            font-size="10"
          >{{ n.label }}</text>
        </g>
      </svg>

      <ul class="rendered-entities">
        <li
          v-for="entity in (execution.result.value?.entities ?? []) as readonly EntityItemSummary[]"
          :key="entity.id"
        >
          {{ entity.name }}
        </li>
      </ul>

      <CandidateReviewPanel
        :candidates="derivedCandidates(execution.result.value?.connections ?? [])"
        :review="review"
        @toggle="toggleDecision"
        @explain="(c) => (explaining = c)"
        @materialize="(c) => (materializing = c)"
      />
    </template>

    <WitnessChainPopover
      v-if="explaining"
      :source-entity-id="explaining.source"
      :target-entity-id="explaining.target"
      :via-connection-ids="explaining.via_connection_ids"
      @close="explaining = null"
    />

    <MaterializeConnectionDialog
      v-if="materializing && materializeTarget"
      :source-entity-id="materializeTarget.source.id"
      :source-entity-type="materializeTarget.source.type"
      :target-entity-id="materializeTarget.target.id"
      :target-entity-name="materializeTarget.target.name"
      :target-entity-type="materializeTarget.target.type"
      :conn-type="materializing.type"
      :hops="materializing.hops"
      @added="materializing = null"
      @cancel="materializing = null"
    />
  </div>
</template>

<style scoped>
.layered-view { padding: 0 0 24px; }
.page-title { font-size: 16px; padding: 12px 16px 0; margin: 0; color: #374151; }
.stale-banner { background: #fef3c7; color: #92400e; padding: 8px 16px; font-size: 12.5px; }
.stale-banner-title { margin: 0 0 6px; font-weight: 600; }
.stale-finding-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.stale-finding { display: flex; gap: 10px; align-items: center; }
.stale-finding-desc { flex: 1; }
.stale-banner button { border: 1px solid #d1d5db; background: white; border-radius: 5px; padding: 2px 8px; cursor: pointer; }
.legend { display: flex; gap: 16px; padding: 8px 16px; font-size: 12px; color: #374151; }
.legend-entry { display: inline-flex; align-items: center; gap: 4px; }
.legend-swatch { width: 20px; height: 0; border-top: 2px dashed #9ca3af; display: inline-block; }
.legend-swatch--certain { border-top-style: dashed; }
.legend-swatch--potential { border-top-style: dotted; }
.graph-svg { width: 100%; height: 400px; background: #fafafa; }
.derived-edge { cursor: pointer; }
.rendered-entities { padding: 4px 16px; font-size: 12px; color: #374151; columns: 3; }
</style>
