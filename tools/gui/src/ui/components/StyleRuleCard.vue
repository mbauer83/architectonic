<script setup lang="ts">
/**
 * One style rule's editor card: capability/mode header, the per-mode fields (match
 * criteria + token, range bands, scale fields), optional endpoint criteria on edge rules
 * (source/target entity predicates — boundary styling), and the quarantined (`disabled`)
 * state with a re-enable affordance.
 */
import type { CriteriaCatalog } from '../../domain'
import type { GroupNode } from '../../domain/viewpointCriteria'
import { mkGroup } from '../../domain/viewpointCriteria'
import { isEdgeCapability, mkRangeBand } from '../../domain/viewpointPresentation'
import type { RangeBandNode, StyleMode, StyleRuleNode } from '../../domain/viewpointPresentation'
import CriteriaTreeBuilder from './CriteriaTreeBuilder.vue'
import StyleRuleScaleFields from './StyleRuleScaleFields.vue'
import StyleValuePicker from './StyleValuePicker.vue'

const props = defineProps<{
  rule: StyleRuleNode
  index: number
  catalog: CriteriaCatalog
  capabilities: readonly string[]
  numericAttributes: readonly string[]
  scaleAttributeOptions: readonly string[]
}>()
const emit = defineEmits<{
  update: [rule: StyleRuleNode]
  remove: []
  move: [delta: number]
  modeChange: [mode: StyleMode]
}>()

const STYLE_MODES: readonly StyleMode[] = ['match', 'range', 'scale']

const patch = (fields: Partial<StyleRuleNode>) => emit('update', { ...props.rule, ...fields })

const updateBand = (bandIndex: number, band: RangeBandNode) => {
  const rangeBands = [...props.rule.rangeBands]
  rangeBands[bandIndex] = band
  patch({ rangeBands })
}

const ENDPOINTS = ['sourceCriteria', 'targetCriteria'] as const
const endpointLabel = (key: typeof ENDPOINTS[number]) => key === 'sourceCriteria' ? 'source endpoint' : 'target endpoint'
</script>

<template>
  <div
    class="rule-card"
    :class="{ 'rule-card--disabled': rule.disabled }"
  >
    <p
      v-if="rule.disabled"
      class="disabled-note"
    >
      Disabled (quarantined) — this rule is kept as inherited but never evaluated.
      <button
        type="button"
        class="reenable-btn"
        @click="patch({ disabled: false })"
      >
        Re-enable
      </button>
    </p>
    <div class="rule-top">
      <span class="rule-order">#{{ index + 1 }}</span>
      <select
        class="inp"
        :value="rule.capability"
        :disabled="rule.disabled"
        @change="patch({ capability: ($event.target as HTMLSelectElement).value })"
      >
        <option
          v-for="capability in capabilities"
          :key="capability"
          :value="capability"
        >
          {{ capability }}
        </option>
      </select>
      <div class="mode-toggle">
        <button
          v-for="mode in STYLE_MODES"
          :key="mode"
          type="button"
          :class="{ sel: rule.mode === mode }"
          :disabled="rule.disabled"
          @click="emit('modeChange', mode)"
        >
          {{ mode }}
        </button>
      </div>
      <button
        type="button"
        class="icon-btn move-btn"
        @click="emit('move', -1)"
      >
        ↑
      </button>
      <button
        type="button"
        class="icon-btn move-btn"
        @click="emit('move', 1)"
      >
        ↓
      </button>
      <button
        type="button"
        class="icon-btn"
        @click="emit('remove')"
      >
        ✕
      </button>
    </div>

    <template v-if="!rule.disabled">
      <template v-if="rule.mode === 'match'">
        <CriteriaTreeBuilder
          v-if="rule.matchCriteria"
          :model-value="rule.matchCriteria"
          :group-kind="isEdgeCapability(rule.capability) ? 'connection' : 'entity'"
          :catalog="catalog"
          is-root
          @update:model-value="patch({ matchCriteria: $event })"
        />
        <label class="value-line">
          value:
          <StyleValuePicker
            :model-value="rule.value"
            @update:model-value="patch({ value: $event || null })"
          />
        </label>
      </template>

      <template v-else-if="rule.mode === 'range'">
        <label class="value-line">
          range_attribute:
          <select
            class="inp"
            :value="rule.rangeAttribute ?? ''"
            @change="patch({ rangeAttribute: ($event.target as HTMLSelectElement).value || null })"
          >
            <option value="" />
            <option
              v-for="attr in numericAttributes"
              :key="attr"
              :value="attr"
            >
              {{ attr }}
            </option>
          </select>
        </label>
        <div
          v-for="(band, bandIndex) in rule.rangeBands"
          :key="band.id"
          class="band-row"
        >
          <input
            class="inp band-input"
            type="number"
            placeholder="-inf"
            :value="band.minimum ?? ''"
            @input="updateBand(bandIndex, { ...band, minimum: ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value) })"
          >
          <span>to</span>
          <input
            class="inp band-input"
            type="number"
            placeholder="+inf"
            :value="band.maximum ?? ''"
            @input="updateBand(bandIndex, { ...band, maximum: ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value) })"
          >
          <StyleValuePicker
            :model-value="band.value"
            @update:model-value="updateBand(bandIndex, { ...band, value: $event })"
          />
          <button
            type="button"
            class="icon-btn"
            @click="patch({ rangeBands: rule.rangeBands.filter((_, i) => i !== bandIndex) })"
          >
            ✕
          </button>
        </div>
        <button
          type="button"
          class="add-btn"
          @click="patch({ rangeBands: [...rule.rangeBands, mkRangeBand()] })"
        >
          + Add band
        </button>
      </template>

      <StyleRuleScaleFields
        v-else
        :model-value="rule"
        :attribute-options="scaleAttributeOptions"
        @update:model-value="emit('update', $event)"
      />

      <div
        v-if="isEdgeCapability(rule.capability)"
        class="endpoint-block"
      >
        <template
          v-for="key in ENDPOINTS"
          :key="key"
        >
          <div
            v-if="rule[key]"
            class="endpoint-group"
          >
            <div class="endpoint-head">
              <span class="endpoint-label">{{ endpointLabel(key) }} must match</span>
              <button
                type="button"
                class="icon-btn"
                :aria-label="`Remove ${endpointLabel(key)} criteria`"
                @click="patch({ [key]: null })"
              >
                ✕
              </button>
            </div>
            <CriteriaTreeBuilder
              :model-value="rule[key] as GroupNode"
              group-kind="entity"
              :catalog="catalog"
              is-root
              @update:model-value="patch({ [key]: $event })"
            />
          </div>
          <button
            v-else
            type="button"
            class="add-btn endpoint-add"
            :title="`Restrict this rule to edges whose ${endpointLabel(key)} entity matches criteria (e.g. a group boundary)`"
            @click="patch({ [key]: mkGroup('entity') })"
          >
            + {{ endpointLabel(key) }} criteria
          </button>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.rule-card { border: 1px solid #d1d5db; border-radius: 8px; padding: 10px; background: #fff; margin: 6px 0; }
.rule-card--disabled { background: #f9fafb; border-style: dashed; }
.disabled-note { font-size: 12px; color: #92400e; background: #fef3c7; border-radius: 6px; padding: 6px 10px; margin: 0 0 8px; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.reenable-btn { appearance: none; border: 1px solid #d1d5db; background: #fff; color: #374151; border-radius: 5px; font-size: 11px; font-weight: 600; padding: 2px 8px; cursor: pointer; flex-shrink: 0; }
.reenable-btn:hover { border-color: #6366f1; color: #4338ca; }
.rule-top { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.rule-order { font-family: monospace; font-size: 11px; color: #9ca3af; background: #f3f4f6; border-radius: 5px; padding: 2px 6px; }
.mode-toggle { display: inline-flex; border: 1px solid #d1d5db; border-radius: 99px; overflow: hidden; }
.mode-toggle button { appearance: none; border: none; background: #fff; color: #6b7280; font-size: 11px; font-weight: 700; padding: 3px 10px; cursor: pointer; }
.mode-toggle button.sel { background: #6366f1; color: #fff; }
.mode-toggle button:disabled { cursor: not-allowed; opacity: .6; }
.value-line { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: #6b7280; margin-top: 8px; }
.band-row { display: flex; gap: 6px; align-items: center; margin: 4px 0; }
.band-input { width: 72px; }
.inp { padding: 4px 6px; border-radius: 5px; border: 1px solid #d1d5db; font-size: 12.5px; font-family: inherit; }
.icon-btn { appearance: none; border: none; background: none; color: #9ca3af; cursor: pointer; font-size: 15px; line-height: 1; padding: 2px 5px; border-radius: 5px; }
.icon-btn:hover { background: #fee2e2; color: #991b1b; }
.move-btn { color: #6b7280; font-size: 13px; }
.move-btn:hover { background: #eef2ff; color: #4338ca; }
.add-btn { appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280; border-radius: 7px; padding: 5px 10px; font-size: 12px; font-weight: 600; cursor: pointer; }
.add-btn:hover { border-color: #6366f1; color: #4338ca; }
.endpoint-block { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.endpoint-add { align-self: flex-start; font-size: 11.5px; }
.endpoint-group { border: 1px dashed #c7d2fe; border-radius: 7px; padding: 8px; background: #fafaff; }
.endpoint-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.endpoint-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #4338ca; }
</style>
