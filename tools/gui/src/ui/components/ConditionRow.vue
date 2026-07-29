<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import type { CriteriaCatalog } from '../../domain'
import type { Comparator, ConditionNode, GroupKind, ValueRef } from '../../domain/viewpointCriteria'
import { bindingValue, literalValue } from '../../domain/viewpointCriteria'
import {
  HIGHLIGHTED_NODE_ID_KEY, attributeOptionLabel, attributeOptions, comparatorsFor,
  conditionCoherenceIssue, enumChoicesFor, isEntityReferencePath,
} from './CriteriaTreeBuilder.helpers'
import ValueRefInput from './ValueRefInput.vue'
import EnumChipMultiSelect from './EnumChipMultiSelect.vue'
import EntityRefValueInput from './EntityRefValueInput.vue'

const props = withDefaults(defineProps<{
  modelValue: ConditionNode
  groupKind: GroupKind
  catalog: CriteriaCatalog
  bindingNames?: readonly string[]
  parameterNames?: readonly string[]
}>(), { bindingNames: () => [], parameterNames: () => [] })
const emit = defineEmits<{ 'update:modelValue': [value: ConditionNode]; remove: [] }>()

const highlightedNodeId = inject(HIGHLIGHTED_NODE_ID_KEY, ref(null))

const attributes = computed(() => attributeOptions(props.groupKind, props.catalog))
const attributePaths = computed(() => attributes.value.map((a) => a.path))
const currentAttribute = computed(
  () => attributes.value.find((a) => a.path === props.modelValue.attribute) ?? attributes.value[0],
)
const comparatorChoices = computed(() => comparatorsFor(currentAttribute.value))
const literalChoices = computed(() => enumChoicesFor(props.modelValue.attribute, props.groupKind, props.catalog))
const isEntityRef = computed(() => isEntityReferencePath(props.modelValue.attribute))
const valueTakesNoInput = computed(() => props.modelValue.comparator === 'exists' || props.modelValue.comparator === 'absent')
const valueTakesList = computed(() => props.modelValue.comparator === 'in' || props.modelValue.comparator === 'not_in')
const listValueText = computed(() => {
  const value = props.modelValue.value
  return value.kind === 'literal' && Array.isArray(value.literal) ? value.literal.join(', ') : ''
})
/** Current fixed-list values as a string array (empty unless a literal list is set) —
 * feeds the chip/entity-picker list widgets when the attribute is enumerable / an id. */
const listValues = computed<string[]>(() => {
  const value = props.modelValue.value
  return value.kind === 'literal' && Array.isArray(value.literal) ? value.literal.map((v) => String(v)) : []
})
/** `in`/`not_in` accept either a fixed list of values or a set-valued binding, projected
 * to a scalar list (`{from: binding, name: x, project: id}` — "entity is in set x", no new
 * node kind per the spec). No aggregate/quantifier here: an aggregated binding collapses
 * to a scalar, and a membership test's right-hand side is the whole list itself. */
const listValueIsBinding = computed(() => props.modelValue.value.kind === 'binding')

const coherenceIssue = computed(() => conditionCoherenceIssue(props.modelValue))

const update = (patch: Partial<ConditionNode>) => emit('update:modelValue', { ...props.modelValue, ...patch })

const onAttributeChange = (event: Event) => {
  const attribute = (event.target as HTMLSelectElement).value
  const nextComparators = comparatorsFor(attributes.value.find((a) => a.path === attribute) ?? attributes.value[0])
  const comparator = nextComparators.includes(props.modelValue.comparator) ? props.modelValue.comparator : nextComparators[0]
  update({ attribute, comparator, value: literalValue('') })
}

const onComparatorChange = (event: Event) => {
  const comparator = (event.target as HTMLSelectElement).value as Comparator
  const takesList = comparator === 'in' || comparator === 'not_in'
  // exists/absent take NO value: seed the unset literal (null) — the serializer omits it,
  // so the saved mapping can never trip the server's "takes no value" check.
  const value = comparator === 'exists' || comparator === 'absent'
    ? literalValue(null)
    : takesList ? literalValue([]) : literalValue('')
  update({ comparator, value })
}

const onValueChange = (value: ValueRef) => update({ value })
const onListValueChange = (raw: string) =>
  update({ value: literalValue(raw.split(',').map((v) => v.trim()).filter((v) => v.length > 0)) })
const onListValuesChange = (values: string[]) => update({ value: literalValue(values) })
const onListSourceChange = (source: 'literal' | 'binding') =>
  update({ value: source === 'binding' ? bindingValue(props.bindingNames[0] ?? '') : literalValue([]) })
const onListBindingChange = (patch: { binding?: string; project?: string }) => {
  if (props.modelValue.value.kind !== 'binding') return
  const current = props.modelValue.value
  update({ value: bindingValue(patch.binding ?? current.binding, { project: patch.project !== undefined ? (patch.project || null) : current.project }) })
}
</script>

<template>
  <div
    class="row"
    :class="{ highlighted: highlightedNodeId === modelValue.id }"
  >
    <select
      class="inp attr"
      aria-label="attribute"
      :value="modelValue.attribute"
      @change="onAttributeChange"
    >
      <option
        v-for="attribute in attributes"
        :key="attribute.path"
        :value="attribute.path"
      >
        {{ attributeOptionLabel(attribute) }}
      </option>
    </select>

    <select
      class="inp cmp"
      aria-label="comparator"
      :value="modelValue.comparator"
      @change="onComparatorChange"
    >
      <option
        v-for="comparator in comparatorChoices"
        :key="comparator"
        :value="comparator"
      >
        {{ comparator }}
      </option>
    </select>

    <template v-if="valueTakesList">
      <select
        v-if="bindingNames.length > 0"
        class="inp list-source"
        aria-label="value source"
        :value="listValueIsBinding ? 'binding' : 'literal'"
        @change="onListSourceChange(($event.target as HTMLSelectElement).value as 'literal' | 'binding')"
      >
        <option value="literal">
          fixed values
        </option>
        <option value="binding">
          a named binding's values
        </option>
      </select>
      <EntityRefValueInput
        v-if="!listValueIsBinding && isEntityRef"
        multiple
        :model-value="listValues"
        @update:model-value="onListValuesChange($event as string[])"
      />
      <EnumChipMultiSelect
        v-else-if="!listValueIsBinding && literalChoices"
        :model-value="listValues"
        :choices="literalChoices"
        @update:model-value="onListValuesChange"
      />
      <input
        v-else-if="!listValueIsBinding"
        class="inp val"
        type="text"
        placeholder="comma-separated values"
        :value="listValueText"
        @input="onListValueChange(($event.target as HTMLInputElement).value)"
      >
      <template v-else-if="modelValue.value.kind === 'binding'">
        <select
          class="inp val"
          :value="modelValue.value.binding"
          @change="onListBindingChange({ binding: ($event.target as HTMLSelectElement).value })"
        >
          <option
            v-for="name in bindingNames"
            :key="name"
            :value="name"
          >
            {{ name }}
          </option>
        </select>
        <input
          class="inp val"
          type="text"
          placeholder="project attribute (required)"
          :value="modelValue.value.project ?? ''"
          @input="onListBindingChange({ project: ($event.target as HTMLInputElement).value })"
        >
      </template>
    </template>
    <ValueRefInput
      v-else-if="!valueTakesNoInput"
      :model-value="modelValue.value"
      :group-kind="groupKind"
      :attribute-paths="attributePaths"
      :literal-choices="literalChoices"
      :entity-reference="isEntityRef"
      :binding-names="bindingNames"
      :parameter-names="parameterNames"
      @update:model-value="onValueChange"
    />

    <button
      type="button"
      class="not-toggle"
      :class="{ on: modelValue.negate }"
      title="negate this condition"
      :aria-pressed="modelValue.negate"
      aria-label="Negate this condition"
      @click="update({ negate: !modelValue.negate })"
    >
      NOT
    </button>
    <button
      type="button"
      class="icon-btn"
      title="remove condition"
      aria-label="Remove condition"
      @click="emit('remove')"
    >
      ✕
    </button>
    <span
      v-if="coherenceIssue"
      class="inline-issue"
      role="alert"
    >{{ coherenceIssue }}</span>
  </div>
</template>

<style scoped>
.row {
  display: flex; gap: 6px; align-items: center; background: #fff; border: 1px solid #d1d5db;
  border-radius: 7px; padding: 6px 8px; margin: 5px 0; flex-wrap: wrap;
}
.row.highlighted { outline: 2px solid #dc2626; outline-offset: 2px; }
.inp { padding: 4px 6px; border-radius: 5px; border: 1px solid #d1d5db; font-size: 12.5px; font-family: inherit; }
.attr { min-width: 118px; }
.cmp { min-width: 80px; }
.val { min-width: 90px; flex: 1; }
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
.inline-issue { flex-basis: 100%; font-size: 11px; color: #b45309; }
</style>
