<script setup lang="ts">
/**
 * The one reusable criteria-tree builder: reused unmodified for query filtering, neighbor
 * inclusion, style-rule match mode, and matrix axis criteria — every call site just binds
 * a different `GroupNode` and supplies `groupKind`. Flat-AND at the root (no chrome),
 * opt-in boxed nested groups, per-node NOT, and a recursive incident-condition box (its
 * own two optional criteria legs).
 *
 * Immutable prop-down/emit-up throughout (`vue/no-mutating-props`): every mutation,
 * however deep, rebuilds the touched node and its ancestors up to this component's own
 * `modelValue` and emits `update:modelValue` — the parent (another `CriteriaTreeBuilder`
 * instance, or the management view) is the one that actually assigns it.
 */
import { computed, inject, ref } from 'vue'
import type { CriteriaCatalog } from '../../domain'
import type {
  Conjunction, CriteriaNode, GroupKind, GroupNode, IncidentDirection, IncidentNode, IncidentTraversal,
} from '../../domain/viewpointCriteria'
import { mkCondition, mkGroup, mkIncident } from '../../domain/viewpointCriteria'
import { HIGHLIGHTED_NODE_ID_KEY, atDepthCap, attributeOptions, depthLabel } from './CriteriaTreeBuilder.helpers'
import ConditionRow from './ConditionRow.vue'
import OptionalCriteriaSlot from './OptionalCriteriaSlot.vue'

const highlightedNodeId = inject(HIGHLIGHTED_NODE_ID_KEY, ref(null))

const props = withDefaults(defineProps<{
  modelValue: GroupNode
  groupKind: GroupKind
  catalog: CriteriaCatalog
  depth?: number
  isRoot?: boolean
  bindingNames?: readonly string[]
  parameterNames?: readonly string[]
}>(), { depth: 0, isRoot: false, bindingNames: () => [], parameterNames: () => [] })
const emit = defineEmits<{ 'update:modelValue': [value: GroupNode]; remove: [] }>()

const emitUpdate = (patch: Partial<GroupNode>) => emit('update:modelValue', { ...props.modelValue, ...patch })

const updateChild = (index: number, child: CriteriaNode) => {
  const children = [...props.modelValue.children]
  children[index] = child
  emitUpdate({ children })
}
const removeChild = (index: number) => emitUpdate({ children: props.modelValue.children.filter((_, i) => i !== index) })

const defaultAttribute = computed(() => attributeOptions(props.groupKind, props.catalog)[0]?.path ?? 'type')

const addCondition = () => emitUpdate({ children: [...props.modelValue.children, mkCondition(defaultAttribute.value)] })
const addGroup = (conjunction: Conjunction) => {
  const group = mkGroup(props.groupKind, conjunction)
  group.children = [mkCondition(defaultAttribute.value)]
  emitUpdate({ children: [...props.modelValue.children, group] })
}
const addIncident = () => emitUpdate({ children: [...props.modelValue.children, mkIncident()] })

const updateIncident = (index: number, patch: Partial<IncidentNode>) => {
  const current = props.modelValue.children[index]
  if (current.kind !== 'incident') return
  updateChild(index, { ...current, ...patch })
}

const atCap = computed(() => atDepthCap(props.depth))
</script>

<template>
  <div
    class="group-box"
    :class="[isRoot ? 'root' : 'nested', { highlighted: highlightedNodeId === modelValue.id }]"
  >
    <div
      v-if="!isRoot"
      class="group-controls"
    >
      <span class="match-line">
        Match
        <select
          class="conj-select"
          aria-label="match mode"
          :value="modelValue.conjunction"
          @change="emitUpdate({ conjunction: ($event.target as HTMLSelectElement).value as Conjunction })"
        >
          <option value="and">
            ALL
          </option>
          <option value="or">
            ANY
          </option>
        </select>
        of these:
      </span>
      <button
        type="button"
        class="not-toggle"
        :class="{ on: modelValue.negate }"
        title="negate the whole group"
        :aria-pressed="modelValue.negate"
        aria-label="Negate this group"
        @click="emitUpdate({ negate: !modelValue.negate })"
      >
        NOT
      </button>
      <button
        type="button"
        class="icon-btn"
        title="remove group"
        aria-label="Remove group"
        @click="emit('remove')"
      >
        ✕
      </button>
      <span class="depth-tag">{{ depthLabel(depth) }}</span>
    </div>
    <div
      v-else-if="modelValue.children.length > 1"
      class="connector"
    >
      {{ modelValue.conjunction.toUpperCase() }}
    </div>

    <template
      v-for="(child, index) in modelValue.children"
      :key="child.id"
    >
      <ConditionRow
        v-if="child.kind === 'condition'"
        :model-value="child"
        :group-kind="groupKind"
        :catalog="catalog"
        :binding-names="bindingNames"
        :parameter-names="parameterNames"
        @update:model-value="updateChild(index, $event)"
        @remove="removeChild(index)"
      />
      <CriteriaTreeBuilder
        v-else-if="child.kind === 'group'"
        :model-value="child"
        :group-kind="groupKind"
        :catalog="catalog"
        :depth="depth + 1"
        :binding-names="bindingNames"
        :parameter-names="parameterNames"
        @update:model-value="updateChild(index, $event)"
        @remove="removeChild(index)"
      />
      <div
        v-else
        class="incident-box"
        :class="{ highlighted: highlightedNodeId === child.id }"
      >
        <div class="incident-head">
          <b>has a</b>
          <select
            class="conj-select"
            aria-label="connection traversal"
            :value="child.traversal"
            @change="updateIncident(index, { traversal: ($event.target as HTMLSelectElement).value as IncidentTraversal })"
          >
            <option value="direct">
              direct
            </option>
            <option value="derived">
              derived
            </option>
            <option value="both">
              direct or derived
            </option>
          </select>
          <b>connection</b>
          <select
            class="conj-select"
            aria-label="connection direction"
            :value="child.direction"
            @change="updateIncident(index, { direction: ($event.target as HTMLSelectElement).value as IncidentDirection })"
          >
            <option value="either">
              (either direction)
            </option>
            <option value="outgoing">
              outgoing
            </option>
            <option value="incoming">
              incoming
            </option>
          </select>
          <button
            type="button"
            class="not-toggle"
            :class="{ on: child.negate }"
            title="negate: has NO such connection"
            :aria-pressed="child.negate"
            aria-label="Negate: has no such connection"
            @click="updateIncident(index, { negate: !child.negate })"
          >
            NOT
          </button>
          <button
            type="button"
            class="icon-btn"
            title="remove"
            aria-label="Remove connection condition"
            @click="removeChild(index)"
          >
            ✕
          </button>
        </div>
        <div class="incident-sub">
          <OptionalCriteriaSlot
            :model-value="child.connectionCriteria"
            group-kind="connection"
            :catalog="catalog"
            :depth="depth + 1"
            :binding-names="bindingNames"
            :parameter-names="parameterNames"
            field-label="connection_criteria"
            unrestricted-label="any connection"
            @update:model-value="updateIncident(index, { connectionCriteria: $event })"
          />
          <span class="sub-label">…to an entity where:</span>
          <OptionalCriteriaSlot
            :model-value="child.endpointCriteria"
            group-kind="entity"
            :catalog="catalog"
            :depth="depth + 1"
            :binding-names="bindingNames"
            :parameter-names="parameterNames"
            field-label="endpoint_criteria"
            unrestricted-label="any entity"
            @update:model-value="updateIncident(index, { endpointCriteria: $event })"
          />
        </div>
      </div>
    </template>

    <div class="add-row">
      <button
        type="button"
        class="add-btn"
        @click="addCondition"
      >
        + Add condition
      </button>
      <button
        v-if="!atCap"
        type="button"
        class="add-btn"
        @click="addGroup('or')"
      >
        + Add group (AND/OR)
      </button>
      <button
        v-if="groupKind === 'entity' && !atCap"
        type="button"
        class="add-btn"
        @click="addIncident"
      >
        + Add "has a connection…"
      </button>
    </div>
  </div>
</template>

<style scoped>
.group-box { border-radius: 8px; padding: 10px; margin: 6px 0; }
.group-box.nested { border: 1px solid #d1d5db; background: #f9fafb; }
.group-box.root { padding: 0; }
.group-box.highlighted, .incident-box.highlighted { outline: 2px solid #dc2626; outline-offset: 2px; }
.group-controls { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
.match-line { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: #6b7280; }
.conj-select {
  font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 6px; border: 1px solid #6366f1;
  color: #4338ca; background: #eef2ff;
}
.not-toggle {
  appearance: none; border: 1px solid #d1d5db; border-radius: 99px; background: #fff;
  color: #9ca3af; font-size: 10.5px; font-weight: 700; padding: 3px 9px; cursor: pointer;
}
.not-toggle.on { background: #fee2e2; color: #991b1b; border-color: transparent; }
.icon-btn {
  appearance: none; border: none; background: none; color: #9ca3af; cursor: pointer;
  font-size: 15px; line-height: 1; padding: 2px 5px; border-radius: 5px;
}
.icon-btn:hover { background: #fee2e2; color: #991b1b; }
.depth-tag { font-size: 11px; color: #9ca3af; background: #f3f4f6; padding: 2px 8px; border-radius: 99px; }
.connector { font-size: 10.5px; font-weight: 700; letter-spacing: .04em; color: #9ca3af; margin: 2px 0 2px 4px; }
.incident-box { border: 1px solid #d1d5db; border-radius: 7px; padding: 8px; margin: 5px 0; background: #fff; }
.incident-head { display: flex; align-items: center; gap: 8px; font-size: 12.5px; font-weight: 600; flex-wrap: wrap; }
.incident-sub { margin: 8px 0 0 16px; padding-left: 10px; border-left: 2px solid #d1d5db; }
.sub-label { display: block; font-size: 11px; color: #9ca3af; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; margin: 6px 0 4px; }
.add-row { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.add-btn {
  appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280;
  border-radius: 7px; padding: 5px 10px; font-size: 12px; font-weight: 600; cursor: pointer;
}
.add-btn:hover { border-color: #6366f1; color: #4338ca; }
</style>
