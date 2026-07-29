<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { GraphEdge } from '../composables/useForceGraph'
import type { ConnectionItemSummary } from '../../domain'
import { friendlyEntityName } from '../views/GraphExploreView.helpers'

/** Detail-panel content for a selected graph edge: type, endpoints, description, and —
 * for a derived connection — its provenance (certainty, modeled hop count, and the
 * server-ordered witness chain with every underlying modeled connection addressable).
 * A derived edge whose chain could not be reconstructed says so explicitly. */
const props = defineProps<{
  edge: GraphEdge
  summary: ConnectionItemSummary | null
}>()

const isDerived = computed(() => props.summary?.certainty != null)
const steps = computed(() => props.summary?.witness_steps ?? [])
</script>

<template>
  <div class="detail-field">
    <label>Connection type</label><span class="detail-value mono">{{ edge.connType }}</span>
  </div>
  <div
    v-if="edge.srcMultiplicity || edge.tgtMultiplicity"
    class="detail-field"
  >
    <label>Multiplicity</label>
    <span class="detail-value mono">
      {{ edge.srcMultiplicity || '?' }} → {{ edge.tgtMultiplicity || '?' }}
    </span>
  </div>
  <div class="detail-field">
    <label>Source</label>
    <RouterLink
      :to="{ path: '/entity', query: { id: edge.source } }"
      class="detail-value detail-link"
    >
      {{ friendlyEntityName(edge.source) }}
    </RouterLink>
  </div>
  <div class="detail-field">
    <label>Target</label>
    <RouterLink
      :to="{ path: '/entity', query: { id: edge.target } }"
      class="detail-value detail-link"
    >
      {{ friendlyEntityName(edge.target) }}
    </RouterLink>
  </div>
  <div class="detail-field">
    <label>Provenance</label>
    <span
      v-if="!isDerived"
      class="detail-value"
    >modeled connection</span>
    <span
      v-else
      class="detail-value"
    >derived ({{ summary?.certainty }}), {{ summary?.hops }} modeled hops</span>
  </div>
  <div
    v-if="isDerived"
    class="detail-content"
  >
    <label>Witness chain</label>
    <ol
      v-if="steps.length > 0"
      class="witness-steps"
    >
      <li
        v-for="step in steps"
        :key="step.connection_id"
      >
        <span class="mono">{{ step.connection_type }}</span>:
        <RouterLink
          :to="{ path: '/entity', query: { id: step.direction === 'forward' ? step.source : step.target } }"
          class="detail-link"
        >
          {{ friendlyEntityName(step.direction === 'forward' ? step.source : step.target) }}
        </RouterLink>
        →
        <RouterLink
          :to="{ path: '/entity', query: { id: step.direction === 'forward' ? step.target : step.source } }"
          class="detail-link"
        >
          {{ friendlyEntityName(step.direction === 'forward' ? step.target : step.source) }}
        </RouterLink>
      </li>
    </ol>
    <div
      v-else
      class="witness-unavailable"
    >
      witness chain unavailable — an underlying modeled connection may have changed since
      this relationship was derived
    </div>
  </div>
  <div
    v-if="edge.description?.trim()"
    class="detail-content"
  >
    <label>Description</label>
    <div class="content-body">
      {{ edge.description.trim() }}
    </div>
  </div>
</template>

<style scoped>
.detail-field { display: flex; flex-direction: column; gap: 2px; margin-bottom: 10px; }
.detail-field label, .detail-content label { font-size: 10.5px; text-transform: uppercase; letter-spacing: .04em; color: #9ca3af; }
.detail-value { font-size: 13px; color: #111827; }
.detail-value.mono, .mono { font-family: ui-monospace, monospace; font-size: 12px; }
.detail-link { color: #2563eb; text-decoration: none; }
.detail-link:hover { text-decoration: underline; }
.detail-content { margin-bottom: 10px; }
.content-body { font-size: 12.5px; color: #374151; white-space: pre-wrap; }
.witness-steps { margin: 4px 0 0; padding-left: 18px; font-size: 12.5px; color: #374151; }
.witness-steps li { margin-bottom: 2px; }
.witness-unavailable { font-size: 12px; color: #b45309; }
</style>
