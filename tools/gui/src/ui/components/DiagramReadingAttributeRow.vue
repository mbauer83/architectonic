<script setup lang="ts">
/**
 * One attribute, as the reading panel offers it: what it is, how much of it is there, and the choices.
 *
 * Its own component because the panel offers the same row in two places — once under each type that
 * declares an attribute, and once at the top for an attribute several types declare identically. Those
 * differ in exactly two ways: the shared row carries how many types it spans, and only a per-type row
 * unfolds the colour key. Everything else was written twice for one commit, which is one commit too
 * many: the two would have drifted on the first control added to either.
 *
 * **Every option is a checkbox.** Colour and print are independent yes/no choices, and a legend will be
 * a third. Colouring admits at most one yes because a fill can only be one colour — a fact about a
 * fill, not a rule about the control, which is why it is not a radio group.
 */
import type { AttributeOffer } from '../../domain/schemas/diagrams'
import { withDeclaredColours, type ReadingLens } from '../../domain/readingLens'
import {
  canTakeColour, hasCustomColours, presenceLabel, valueSetLabel, withColourBy, withPrinted,
  type ColourStep,
} from './DiagramReadingPanel.helpers'

defineProps<{
  attribute: AttributeOffer
  lens: ReadingLens
  /** The rows a shared attribute spans, for the "N types" chip. Absent on a per-type row. */
  onRows?: readonly string[]
  /** The colour mapping to unfold when this attribute is the one being coloured by. A shared row
   * passes none: the key belongs beside one control, and showing it twice would invite a reader to
   * wonder which of the two the picture used. */
  colourKey?: readonly ColourStep[]
}>()
const emit = defineEmits<{ 'update:lens': [ReadingLens]; pick: [ColourStep, string] }>()

/** Why an attribute is offered no colour, on hover. The row's declared type says it too, but only to
 * a reader who already knows that a ramp needs an order and a palette a bounded set. */
const NO_COLOUR_REASON =
  'A ramp needs an order and a palette needs a bounded set of values; this attribute declares neither.'
</script>

<template>
  <li class="attr">
    <div class="attr__row">
      <span class="attr__name">{{ attribute.name }}</span>
      <span class="attr__type">{{ attribute.declared_type }}</span>
      <span
        v-if="valueSetLabel(attribute)"
        class="attr__values"
        title="A bounded set of values is what a palette needs; free text has none"
      >{{ valueSetLabel(attribute) }}</span>
      <span
        class="attr__presence"
        :class="{ 'attr__presence--none': attribute.present_on === 0 }"
      >
        {{ presenceLabel(attribute) }}
      </span>
      <span
        v-if="onRows"
        class="attr__rows"
        :title="`Declared by ${onRows.join(', ')}`"
      >{{ onRows.length }} types</span>
      <span class="attr__controls">
        <label
          v-if="canTakeColour(attribute)"
          class="attr__control"
        >
          <input
            type="checkbox"
            :checked="lens.colourBy === attribute.name"
            @change="emit('update:lens', withColourBy(lens, attribute.name))"
          >
          colour
        </label>
        <span
          v-else
          class="attr__control attr__control--absent"
          :title="NO_COLOUR_REASON"
        >no colour</span>
        <label class="attr__control">
          <input
            type="checkbox"
            :checked="lens.printed.includes(attribute.name)"
            @change="emit('update:lens', withPrinted(lens, attribute.name))"
          >
          print
        </label>
      </span>
    </div>

    <div
      v-if="colourKey && lens.colourBy === attribute.name"
      class="key"
    >
      <label
        v-for="step in colourKey"
        :key="step.label"
        class="key__step"
      >
        <input
          class="key__swatch"
          type="color"
          :value="step.colour"
          :title="`Pick the colour for ${step.label}`"
          @input="emit('pick', step, ($event.target as HTMLInputElement).value)"
        >
        {{ step.label }}
      </label>
      <span
        v-if="attribute.colour === 'ramp'"
        class="key__note"
      >values in between shade between these</span>
      <button
        v-if="hasCustomColours(attribute, lens)"
        class="key__revert"
        type="button"
        @click="emit('update:lens', withDeclaredColours(lens, attribute.values))"
      >
        declared colours
      </button>
    </div>
  </li>
</template>

<style scoped>
.attr { padding: 0.15rem 0; }
.attr__row { display: flex; align-items: baseline; gap: 0.5rem; }
.attr__name { font-family: ui-monospace, monospace; }
.attr__type, .attr__presence, .attr__rows, .attr__values { color: #6b7280; font-size: 0.8rem; }
.attr__presence--none { color: #d97706; }
/* The controls are one group pushed to the right, rather than each control finding its own way there:
   "no colour" is a `span` where a colour choice is a `label`, so a `:first-of-type` rule aligned the
   choices and left the absences stranded mid-row. */
.attr__controls { display: inline-flex; align-items: baseline; gap: 0.75rem; margin-left: auto; }
.attr__control { display: inline-flex; align-items: baseline; gap: 0.2rem; cursor: pointer; }
.attr__control--absent { color: #9ca3af; cursor: default; font-size: 0.8rem; }
.key { display: flex; flex-wrap: wrap; align-items: center; gap: 0.6rem; padding: 0.1rem 0 0.3rem; }
.key__step { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.8rem; }
/* A colour input rather than a plain swatch: it *is* the picker, and the browser's own is the one a
   reader already knows. Sized down to a swatch, with the platform chrome stripped so a row of them
   reads as a key rather than as a row of form controls. */
.key__swatch {
  width: 1rem; height: 1rem; padding: 0; border: 1px solid rgb(0 0 0 / 0.2); border-radius: 2px;
  background: none; cursor: pointer; appearance: none; -webkit-appearance: none;
}
.key__swatch::-webkit-color-swatch-wrapper { padding: 0; }
.key__swatch::-webkit-color-swatch { border: none; border-radius: 1px; }
.key__swatch::-moz-color-swatch { border: none; border-radius: 1px; }
.key__note { color: #9ca3af; font-size: 0.75rem; }
.key__revert {
  font: inherit; font-size: 0.75rem; color: #6b7280; background: none; border: none;
  padding: 0; text-decoration: underline; cursor: pointer;
}
.key__revert:hover { color: #374151; }
</style>
