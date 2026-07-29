<script setup lang="ts">
/**
 * Ordered style-rule list (first-match-wins per capability), the default-style fallback
 * map, and the read-only derived legend. Each rule renders through `StyleRuleCard`
 * (per-mode fields, endpoint criteria on edge rules, quarantined state); every style
 * value is picked visually — never typed as free text.
 */
import { computed } from 'vue'
import type { CriteriaCatalog } from '../../domain'
import { mkStyleRule, withStyleMode } from '../../domain/viewpointPresentation'
import type { PresentationNode, StyleMode, StyleRuleNode } from '../../domain/viewpointPresentation'
import { tokenColor } from '../lib/viewpointStyleTokens'
import { capabilitiesFor, derivedLegend, numericAttributeOptions } from './StyleRuleEditor.helpers'
import StyleRuleCard from './StyleRuleCard.vue'
import StyleValuePicker from './StyleValuePicker.vue'

const props = defineProps<{
  modelValue: PresentationNode
  catalog: CriteriaCatalog
  declaredDerivedNames?: readonly string[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: PresentationNode] }>()

const capabilities = computed(() => capabilitiesFor(props.modelValue.representation))
const numericAttributes = computed(() => numericAttributeOptions(props.catalog))
const scaleAttributeOptions = computed(() => [
  ...numericAttributes.value,
  ...(props.declaredDerivedNames ?? []).map((name) => `derived.${name}`),
])
const legend = computed(() => derivedLegend(props.modelValue))

const emitUpdate = (patch: Partial<PresentationNode>) => emit('update:modelValue', { ...props.modelValue, ...patch })

const updateRule = (index: number, rule: StyleRuleNode) => {
  const stylingRules = [...props.modelValue.stylingRules]
  stylingRules[index] = rule
  emitUpdate({ stylingRules })
}
const removeRule = (index: number) => emitUpdate({ stylingRules: props.modelValue.stylingRules.filter((_, i) => i !== index) })
const moveRule = (index: number, delta: number) => {
  const stylingRules = [...props.modelValue.stylingRules]
  const target = index + delta
  if (target < 0 || target >= stylingRules.length) return
  ;[stylingRules[index], stylingRules[target]] = [stylingRules[target], stylingRules[index]]
  emitUpdate({ stylingRules })
}
const addRule = () => emitUpdate({ stylingRules: [...props.modelValue.stylingRules, mkStyleRule(props.modelValue.representation)] })

const onModeChange = (index: number, mode: StyleMode) =>
  updateRule(index, withStyleMode(props.modelValue.stylingRules[index], mode))

const onDefaultStyleChange = (capability: string, token: string) => {
  const defaultStyle = { ...props.modelValue.defaultStyle }
  if (token === '') delete defaultStyle[capability]
  else defaultStyle[capability] = token
  emitUpdate({ defaultStyle })
}
</script>

<template>
  <div class="style-rule-editor">
    <div class="rule-list">
      <StyleRuleCard
        v-for="(rule, index) in modelValue.stylingRules"
        :key="rule.id"
        :rule="rule"
        :index="index"
        :catalog="catalog"
        :capabilities="capabilities"
        :numeric-attributes="numericAttributes"
        :scale-attribute-options="scaleAttributeOptions"
        @update="updateRule(index, $event)"
        @remove="removeRule(index)"
        @move="moveRule(index, $event)"
        @mode-change="onModeChange(index, $event)"
      />
    </div>
    <div class="add-row">
      <button
        type="button"
        class="add-btn"
        @click="addRule"
      >
        + Add style rule
      </button>
    </div>

    <div class="card">
      <b>Default style (fallback when no rule matches)</b>
      <div
        v-for="capability in capabilities"
        :key="capability"
        class="default-row"
      >
        <span>{{ capability }}</span>
        <StyleValuePicker
          :model-value="modelValue.defaultStyle[capability] ?? null"
          allow-scale-endpoints
          clearable
          @update:model-value="onDefaultStyleChange(capability, $event)"
        />
      </div>
    </div>

    <div class="card">
      <div class="legend-header">
        <b>Legend</b>
        <span class="pill">derived — not authored</span>
      </div>
      <p
        v-if="legend.length === 0"
        class="placeholder"
      >
        No style tokens in use yet.
      </p>
      <div
        v-else
        class="legend"
      >
        <span
          v-for="entry in legend"
          :key="entry.token"
          class="legend-item"
        >
          <span
            class="swatch"
            :style="{ background: tokenColor(entry.token) }"
          />
          {{ entry.token }} ({{ entry.usageCount }})
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rule-list { display: flex; flex-direction: column; gap: 8px; }
.add-row { margin-top: 8px; }
.add-btn { appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280; border-radius: 7px; padding: 5px 10px; font-size: 12px; font-weight: 600; cursor: pointer; }
.add-btn:hover { border-color: #6366f1; color: #4338ca; }
.card { border: 1px solid #d1d5db; border-radius: 10px; padding: 12px; margin-top: 12px; }
.default-row {
  display: grid; grid-template-columns: 140px auto; align-items: center;
  column-gap: 16px; margin: 6px 0; font-size: 12.5px;
}
.default-row > span:first-child { color: #374151; }
.legend-header { display: flex; align-items: center; justify-content: space-between; }
.pill { font-size: 11px; font-weight: 600; color: #6b7280; background: #f3f4f6; border-radius: 99px; padding: 2px 8px; }
.legend { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #6b7280; }
.swatch { width: 12px; height: 12px; border-radius: 3px; display: inline-block; border: 1px solid rgba(0,0,0,.15); }
.placeholder { font-size: 12.5px; color: #6b7280; margin: 4px 0; }
</style>
