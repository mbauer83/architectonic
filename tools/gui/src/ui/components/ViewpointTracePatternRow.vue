<script setup lang="ts">
/**
 * One trace pattern's editor row (extracted from `ViewpointTracePatternEditor.vue` for the
 * length policy and cohesion — the editor is the list container, this is one pattern).
 * Progressive disclosure: name / applies-to / diagnostic / branches-mode at the top; branch
 * edges, shortcuts, and the leaf reveal below; a derived leaf's target reveals deepest. Emits
 * a whole replacement `pattern` (never mutates the prop) plus `remove`.
 */
import { inject, ref } from 'vue'
import type { CriteriaCatalog } from '../../domain'
import {
  type DiagnosticStatus,
  type RealizerRegistry,
  type TracePatternNode,
  MAX_EDGE_DECLARATIONS,
  VALID_DIAGNOSTIC_STATUSES,
  VALID_REALIZER_REGISTRIES,
} from '../../domain/viewpointTracePattern'
import { HIGHLIGHTED_NODE_ID_KEY } from './CriteriaTreeBuilder.helpers'
import {
  addBranchEdge, addShortcut, declaredEdgeCount, removeBranchEdge, removeShortcut, setBranchesInline,
  setBranchesRef, setLeafConnection, setLeafDerived, setLeafEndpointKind, setLeafLayerDomain,
  setLeafMaxHops, setLeafNone, setLeafRegistry, toggleMember, updateBranchEdge, updateShortcut,
} from './ViewpointTracePatternEditor.helpers'
import TracePatternEdgeFields from './TracePatternEdgeFields.vue'

defineProps<{
  pattern: TracePatternNode
  catalog: CriteriaCatalog
  layerDomains: readonly string[]
  otherNames: readonly string[]
}>()
const emit = defineEmits<{ update: [value: TracePatternNode]; remove: [] }>()

const highlightedNodeId = inject(HIGHLIGHTED_NODE_ID_KEY, ref<string | null>(null))
const set = (next: TracePatternNode) => emit('update', next)
const input = (e: Event) => (e.target as HTMLInputElement).value
</script>

<template>
  <div
    class="pattern"
    :class="{ highlighted: highlightedNodeId === pattern.id }"
  >
    <div class="pattern-head">
      <input
        class="inp name"
        type="text"
        placeholder="pattern name"
        :value="pattern.name"
        @input="set({ ...pattern, name: input($event) })"
      >
      <label class="check">
        <input
          type="checkbox"
          :checked="pattern.diagnostic"
          @change="set({ ...pattern, diagnostic: ($event.target as HTMLInputElement).checked })"
        > diagnostic (observation, never a gap)
      </label>
      <button
        type="button"
        class="icon-btn"
        @click="emit('remove')"
      >
        ✕
      </button>
    </div>

    <div class="applies">
      <span class="lbl">applies to</span>
      <label
        v-for="type in catalog.entity_types"
        :key="type"
        class="chip"
      >
        <input
          type="checkbox"
          :checked="pattern.appliesTo.includes(type)"
          @change="set({ ...pattern, appliesTo: toggleMember(pattern.appliesTo, type) })"
        > {{ type }}
      </label>
    </div>

    <div class="sub">
      <span class="lbl">branches</span>
      <select
        class="inp"
        :value="pattern.branches.kind"
        @change="set(input($event) === 'ref' ? setBranchesRef(pattern) : setBranchesInline(pattern))"
      >
        <option value="inline">
          declared edges
        </option>
        <option value="ref">
          reuse another pattern's branches (ref)
        </option>
      </select>
      <select
        v-if="pattern.branches.kind === 'ref'"
        class="inp"
        :value="pattern.branches.ref"
        @change="set(setBranchesRef(pattern, input($event)))"
      >
        <option value="">
          — choose pattern —
        </option>
        <option
          v-for="name in otherNames"
          :key="name"
          :value="name"
        >
          {{ name }}
        </option>
      </select>
    </div>

    <div
      v-if="pattern.branches.kind === 'inline'"
      class="edges"
    >
      <div
        v-for="(edge, ei) in pattern.branches.edges"
        :key="edge.id"
        class="edge-row"
      >
        <input
          class="inp label"
          type="text"
          placeholder="edge label"
          :value="edge.label"
          @input="set(updateBranchEdge(pattern, ei, { ...edge, label: input($event) }))"
        >
        <TracePatternEdgeFields
          :connection="edge.connection"
          :direction="edge.direction"
          :endpoint-type="edge.endpointType"
          :catalog="catalog"
          @connection="set(updateBranchEdge(pattern, ei, { ...edge, connection: $event }))"
          @direction="set(updateBranchEdge(pattern, ei, { ...edge, direction: $event }))"
          @endpoint-type="set(updateBranchEdge(pattern, ei, { ...edge, endpointType: $event }))"
        />
        <button
          type="button"
          class="icon-btn"
          @click="set(removeBranchEdge(pattern, ei))"
        >
          ✕
        </button>
      </div>
      <button
        type="button"
        class="add-btn"
        @click="set(addBranchEdge(pattern))"
      >
        + Add branch edge
      </button>
    </div>

    <div class="edges">
      <div
        v-for="(edge, si) in pattern.shortcuts"
        :key="edge.id"
        class="edge-row"
      >
        <span class="lbl">shortcut</span>
        <TracePatternEdgeFields
          :connection="edge.connection"
          :direction="edge.direction"
          :endpoint-type="edge.endpointType"
          :catalog="catalog"
          @connection="set(updateShortcut(pattern, si, { ...edge, connection: $event }))"
          @direction="set(updateShortcut(pattern, si, { ...edge, direction: $event }))"
          @endpoint-type="set(updateShortcut(pattern, si, { ...edge, endpointType: $event }))"
        />
        <select
          class="inp"
          :value="edge.status"
          @change="set(updateShortcut(pattern, si, { ...edge, status: input($event) as DiagnosticStatus }))"
        >
          <option
            v-for="s in VALID_DIAGNOSTIC_STATUSES"
            :key="s"
            :value="s"
          >
            {{ s }}
          </option>
        </select>
        <button
          type="button"
          class="icon-btn"
          @click="set(removeShortcut(pattern, si))"
        >
          ✕
        </button>
      </div>
      <button
        type="button"
        class="add-btn"
        @click="set(addShortcut(pattern))"
      >
        + Add shortcut edge
      </button>
    </div>

    <div class="sub">
      <span class="lbl">leaf</span>
      <select
        class="inp"
        :value="pattern.leaf.kind"
        @change="set(input($event) === 'none' ? setLeafNone(pattern) : setLeafDerived(pattern))"
      >
        <option value="none">
          none — branch completeness only
        </option>
        <option value="derived-reachability">
          derived reachability — require a realizer
        </option>
      </select>
      <template v-if="pattern.leaf.kind === 'derived-reachability'">
        <select
          class="inp"
          :value="pattern.leaf.connection"
          @change="set(setLeafConnection(pattern, input($event)))"
        >
          <option
            v-for="c in catalog.connection_types"
            :key="c"
            :value="c"
          >
            {{ c }}
          </option>
        </select>
        <input
          class="inp hops"
          type="number"
          min="2"
          :max="4"
          :value="pattern.leaf.maxHops"
          @input="set(setLeafMaxHops(pattern, Number(input($event))))"
        >
        <select
          class="inp"
          :value="pattern.leaf.endpoint.kind"
          @change="set(setLeafEndpointKind(pattern, input($event) as 'registry' | 'layer', layerDomains[0] ?? ''))"
        >
          <option value="registry">
            realizer registry
          </option>
          <option value="layer">
            layer membership (diagnostic)
          </option>
        </select>
        <select
          v-if="pattern.leaf.endpoint.kind === 'registry'"
          class="inp"
          :value="pattern.leaf.endpoint.registry"
          @change="set(setLeafRegistry(pattern, input($event) as RealizerRegistry))"
        >
          <option
            v-for="r in VALID_REALIZER_REGISTRIES"
            :key="r"
            :value="r"
          >
            {{ r }}
          </option>
        </select>
        <select
          v-if="pattern.leaf.endpoint.kind === 'layer'"
          class="inp"
          :value="pattern.leaf.endpoint.domain"
          @change="set(setLeafLayerDomain(pattern, input($event)))"
        >
          <option
            v-for="d in layerDomains"
            :key="d"
            :value="d"
          >
            {{ d }}
          </option>
        </select>
      </template>
    </div>

    <p
      v-if="declaredEdgeCount(pattern) > MAX_EDGE_DECLARATIONS"
      class="cap-warn"
    >
      {{ declaredEdgeCount(pattern) }} edges declared — the loader caps a pattern at
      {{ MAX_EDGE_DECLARATIONS }} after reference expansion.
    </p>
  </div>
</template>

<style scoped>
.pattern { border: 1px solid #d1d5db; border-radius: 8px; padding: 10px; margin: 8px 0; }
.pattern.highlighted { outline: 2px solid #dc2626; outline-offset: 2px; }
.pattern-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 12.5px; }
.applies { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin: 8px 0; font-size: 12px; }
.chip {
  display: inline-flex; align-items: center; gap: 4px; padding: 1px 6px;
  border: 1px solid #e5e7eb; border-radius: 12px; color: #374151;
}
.sub { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 6px 0; font-size: 12.5px; }
.edges { margin: 6px 0 6px 12px; }
.edge-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin: 4px 0; font-size: 12.5px; }
.lbl { color: #6b7280; font-weight: 600; font-size: 12px; }
.inp { font-size: 12.5px; padding: 4px 8px; border-radius: 6px; border: 1px solid #d1d5db; background: #fff; }
.inp.name { min-width: 150px; font-weight: 600; }
.inp.label { min-width: 130px; }
.inp.hops { width: 64px; }
.check { display: inline-flex; align-items: center; gap: 6px; color: #374151; cursor: pointer; }
.icon-btn {
  appearance: none; border: none; background: none; color: #9ca3af;
  cursor: pointer; font-size: 15px; margin-left: auto;
}
.icon-btn:hover { color: #991b1b; }
.add-btn {
  appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280;
  border-radius: 7px; padding: 5px 10px; font-size: 12px; font-weight: 600; cursor: pointer;
}
.add-btn:hover { border-color: #6366f1; color: #4338ca; }
.cap-warn { font-size: 12px; color: #92400e; background: #fef3c7; padding: 4px 10px; border-radius: 4px; }
</style>
