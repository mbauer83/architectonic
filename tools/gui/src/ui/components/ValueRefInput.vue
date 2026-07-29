<script setup lang="ts">
import { computed } from 'vue'
import type { AggregateKind } from '../../domain/viewpointBindings'
import type { GroupKind, Quantifier, ValueRef, ValueRefKind } from '../../domain/viewpointCriteria'
import { bindingValue, endpointValue, literalValue, parameterValue, selfValue } from '../../domain/viewpointCriteria'
import { AGGREGATE_CHOICES, QUANTIFIER_CHOICES, valueKindOptions } from './CriteriaTreeBuilder.helpers'
import EntityRefValueInput from './EntityRefValueInput.vue'

const props = defineProps<{
  modelValue: ValueRef
  groupKind: GroupKind
  /** Attribute paths to offer when kind is `self`/`source`/`target` — the "reference
   * another attribute" cases; same option list a condition's own attribute picker uses. */
  attributePaths: readonly string[]
  /** Fixed choices for a literal value (e.g. known entity/connection types), or null for
   * a free-text literal input. */
  literalChoices: readonly string[] | null
  /** When true the literal value is an entity id — picked via the entity picker rather
   * than typed. Takes precedence over `literalChoices` (an id space is not enumerable). */
  entityReference?: boolean
  /** Names of bindings/parameters declared earlier in this query — empty when none exist
   * yet, in which case `valueKindOptions` omits those kinds entirely. */
  bindingNames: readonly string[]
  parameterNames: readonly string[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: ValueRef] }>()

const kindOptions = computed(() => valueKindOptions(props.groupKind, props.bindingNames.length > 0, props.parameterNames.length > 0))

const onKindChange = (event: Event) => {
  const kind = (event.target as HTMLSelectElement).value as ValueRefKind
  if (kind === 'literal') emit('update:modelValue', literalValue(''))
  else if (kind === 'self') emit('update:modelValue', selfValue(props.attributePaths[0] ?? ''))
  else if (kind === 'binding') emit('update:modelValue', bindingValue(props.bindingNames[0] ?? ''))
  else if (kind === 'parameter') emit('update:modelValue', parameterValue(props.parameterNames[0] ?? ''))
  else emit('update:modelValue', endpointValue(kind, props.attributePaths[0] ?? ''))
}

const onReferenceAttributeChange = (event: Event) => {
  const attribute = (event.target as HTMLSelectElement).value
  if (props.modelValue.kind !== 'self' && props.modelValue.kind !== 'source' && props.modelValue.kind !== 'target') return
  emit('update:modelValue', props.modelValue.kind === 'self' ? selfValue(attribute) : endpointValue(props.modelValue.kind, attribute))
}

const onLiteralChange = (raw: string) => emit('update:modelValue', literalValue(raw))

const onParameterChange = (parameter: string) => emit('update:modelValue', parameterValue(parameter))

const onBindingChange = (patch: { binding?: string; project?: string; aggregate?: AggregateKind | ''; quantifier?: Quantifier | '' }) => {
  if (props.modelValue.kind !== 'binding') return
  emit('update:modelValue', bindingValue(patch.binding ?? props.modelValue.binding, {
    project: patch.project !== undefined ? (patch.project || null) : props.modelValue.project,
    aggregate: patch.aggregate !== undefined ? (patch.aggregate || null) : props.modelValue.aggregate,
    quantifier: patch.quantifier !== undefined ? (patch.quantifier || null) : props.modelValue.quantifier,
  }))
}
</script>

<template>
  <span class="value-ref">
    <select
      class="inp val-kind"
      :value="modelValue.kind"
      @change="onKindChange"
    >
      <option
        v-for="option in kindOptions"
        :key="option.kind"
        :value="option.kind"
      >
        {{ option.label }}
      </option>
    </select>

    <select
      v-if="modelValue.kind === 'self' || modelValue.kind === 'source' || modelValue.kind === 'target'"
      class="inp val"
      :value="modelValue.attribute"
      @change="onReferenceAttributeChange"
    >
      <option
        v-for="path in attributePaths"
        :key="path"
        :value="path"
      >
        {{ path }}
      </option>
    </select>

    <select
      v-else-if="modelValue.kind === 'parameter'"
      class="inp val"
      :value="modelValue.parameter"
      @change="onParameterChange(($event.target as HTMLSelectElement).value)"
    >
      <option
        v-for="name in parameterNames"
        :key="name"
        :value="name"
      >
        {{ name }}
      </option>
    </select>

    <template v-else-if="modelValue.kind === 'binding'">
      <select
        class="inp val"
        :value="modelValue.binding"
        @change="onBindingChange({ binding: ($event.target as HTMLSelectElement).value })"
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
        class="inp val binding-project"
        type="text"
        placeholder="project attribute (optional)"
        :value="modelValue.project ?? ''"
        @input="onBindingChange({ project: ($event.target as HTMLInputElement).value })"
      >
      <select
        class="inp val"
        :value="modelValue.aggregate ?? ''"
        @change="onBindingChange({ aggregate: ($event.target as HTMLSelectElement).value as AggregateKind | '' })"
      >
        <option value="">
          (no aggregate)
        </option>
        <option
          v-for="choice in AGGREGATE_CHOICES"
          :key="choice"
          :value="choice"
        >
          {{ choice }}
        </option>
      </select>
      <select
        class="inp val"
        :value="modelValue.quantifier ?? ''"
        @change="onBindingChange({ quantifier: ($event.target as HTMLSelectElement).value as Quantifier | '' })"
      >
        <option value="">
          (no quantifier)
        </option>
        <option
          v-for="choice in QUANTIFIER_CHOICES"
          :key="choice"
          :value="choice"
        >
          {{ choice }} of
        </option>
      </select>
    </template>

    <EntityRefValueInput
      v-else-if="modelValue.kind === 'literal' && entityReference"
      :model-value="String(modelValue.literal ?? '')"
      @update:model-value="onLiteralChange($event as string)"
    />

    <select
      v-else-if="modelValue.kind === 'literal' && literalChoices"
      class="inp val"
      :value="String(modelValue.literal ?? '')"
      @change="onLiteralChange(($event.target as HTMLSelectElement).value)"
    >
      <option
        v-for="choice in literalChoices"
        :key="choice"
        :value="choice"
      >
        {{ choice }}
      </option>
    </select>

    <input
      v-else-if="modelValue.kind === 'literal'"
      class="inp val"
      type="text"
      :value="String(modelValue.literal ?? '')"
      @input="onLiteralChange(($event.target as HTMLInputElement).value)"
    >
  </span>
</template>

<style scoped>
.value-ref { display: inline-flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.val-kind { max-width: 220px; color: #6b7280; }
.val { min-width: 90px; }
.inp { padding: 4px 6px; border-radius: 5px; border: 1px solid #d1d5db; font-size: 12.5px; font-family: inherit; }
</style>
