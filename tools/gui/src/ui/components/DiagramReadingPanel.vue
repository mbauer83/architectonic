<script setup lang="ts">
/**
 * The reading controls for one diagram: colour the elements by an attribute, print values with them.
 *
 * **Unobtrusive by construction.** It is folded away by default and, folded, still says what is
 * active — a reader who set a heat map, scrolled, and came back must not have to reopen the panel to
 * find out why the picture is orange. Inside, one row per entity type and specialization the diagram
 * actually draws, each folding to its attributes; nothing is offered that no drawn element could
 * answer for.
 *
 * **The rows are the server's answer, in the server's order.** Which types occur, which attributes
 * they declare, which of those a colour can read and how many drawn elements carry a value are all
 * `/attribute-panel`'s answers. Re-sorting or re-deciding any of them here would be a second opinion
 * about the model, and the two would disagree on the first schema this component has not seen.
 *
 * **Every option is a checkbox.** Colour and print are independent yes/no choices per attribute, and
 * later a legend will be a third. Colouring happens to admit at most one yes — a fill can only be one
 * colour — so checking a second attribute's colour unchecks the first; that limit is a fact about a
 * fill, not a rule about the control, which is why it is not a radio group. A radio could not be
 * unset by clicking the one already chosen either, so turning a colouring off would have needed a
 * Reset button somewhere else on the page. With checkboxes there is nothing for one to do.
 *
 * **A colouring shows its key, and the key is editable.** Checking `colour` unfolds the mapping under
 * the row: a gradient's two ends, or one swatch per member of a value set. Each swatch is a colour
 * input, so a reader picks the colours they want for the attribute in front of them — no rule to
 * author, no declaration to add, and a picker rather than a hex field to type into. Where they have
 * changed nothing the swatches show the declared colours, which come from the same generated tables
 * the renderer resolves, so an untouched key and its picture cannot disagree.
 */
import { computed, ref } from 'vue'
import type { AttributeOffer, DiagramAttributePanel, TypeOffer } from '../../domain/schemas/diagrams'
import {
  isEmptyLens, withDeclaredColours, withMemberColour, withRampEnd, type ReadingLens,
} from '../../domain/readingLens'
import { AD_HOC_RAMP_TOKENS } from '../../domain/types.generated'
import { tokenColor } from '../lib/viewpointStyleTokens'
import {
  canTakeColour, colourKey, foldSummary, hasCustomColours, lensSummary, presenceLabel, typeOfferLabel,
  withColourBy, withPrinted,
} from './DiagramReadingPanel.helpers'

const props = defineProps<{ panel: DiagramAttributePanel | null; lens: ReadingLens; busy?: boolean }>()
const emit = defineEmits<{ 'update:lens': [ReadingLens] }>()

const open = ref(false)
const unfolded = ref(new Set<string>())

const rowKey = (offer: TypeOffer) => `${offer.entity_type}/${offer.specialization}`
const isUnfolded = (offer: TypeOffer) => unfolded.value.has(rowKey(offer))
const toggleFold = (offer: TypeOffer) => {
  const next = new Set(unfolded.value)
  if (!next.delete(rowKey(offer))) next.add(rowKey(offer))
  unfolded.value = next
}

const summary = computed(() => lensSummary(props.lens))
const active = computed(() => !isEmptyLens(props.lens))

// The two ends of an ad-hoc ramp, resolved through the same adapter every other surface resolves a
// style token through, from the endpoints the server declares. Nothing about the gradient is decided
// here — this is the key to the picture, not a second opinion about it.
const rampEnds: readonly [string, string] = [
  tokenColor(AD_HOC_RAMP_TOKENS[0]),
  tokenColor(AD_HOC_RAMP_TOKENS[1]),
]
const keyFor = (attribute: AttributeOffer) => colourKey(attribute, rampEnds, props.lens)

/** Why an attribute is offered no colour, on hover. The row's declared type says it too, but only to
 * a reader who already knows that a ramp needs an order and a palette a bounded set. */
const NO_COLOUR_REASON =
  'A ramp needs an order and a palette needs a bounded set of values; this attribute declares neither.'

// A colour input always reports `#rrggbb`, which is what the wire and the renderer both want, so the
// value goes through untouched — the server validates it again regardless, because a query string is
// not a trusted source however this page behaves.
const pick = (step: { member?: string; end?: 0 | 1 }, colour: string) => {
  if (step.member !== undefined) emit('update:lens', withMemberColour(props.lens, step.member, colour))
  else if (step.end !== undefined) emit('update:lens', withRampEnd(props.lens, step.end, colour, rampEnds))
}
</script>

<template>
  <section
    class="reading"
    :class="{ 'reading--active': active }"
  >
    <button
      class="reading__toggle"
      type="button"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span
        class="chev"
        :class="{ 'chev--open': open }"
        aria-hidden="true"
      >›</span>
      <span class="reading__title">Reading</span>
      <span
        v-if="summary"
        class="reading__summary"
      >{{ summary }}</span>
      <span
        v-else
        class="reading__hint"
      >colour and print by attribute</span>
      <span
        v-if="busy"
        class="reading__busy"
        role="status"
      >rendering…</span>
    </button>

    <div
      v-if="open"
      class="reading__body"
    >
      <p
        v-if="panel === null"
        class="reading__note"
      >
        Loading what this diagram can be read by…
      </p>
      <p
        v-else-if="panel.types.length === 0"
        class="reading__note"
      >
        This diagram draws no model entities, so there is nothing to colour or print.
      </p>
      <template v-else>
        <div
          v-for="offer in panel.types"
          :key="rowKey(offer)"
          class="type"
        >
          <button
            class="type__head"
            type="button"
            :aria-expanded="isUnfolded(offer)"
            @click="toggleFold(offer)"
          >
            <span
              class="chev"
              :class="{ 'chev--open': isUnfolded(offer) }"
              aria-hidden="true"
            >›</span>
            <span class="type__name">{{ typeOfferLabel(offer) }}</span>
            <span class="type__drawn">{{ offer.drawn }} drawn</span>
            <span class="type__summary">{{ foldSummary(offer, lens) }}</span>
          </button>

          <ul
            v-if="isUnfolded(offer) && offer.attributes.length"
            class="attrs"
          >
            <li
              v-for="attribute in offer.attributes"
              :key="attribute.name"
              class="attr"
            >
              <div class="attr__row">
                <span class="attr__name">{{ attribute.name }}</span>
                <span class="attr__type">{{ attribute.declared_type }}</span>
                <span
                  class="attr__presence"
                  :class="{ 'attr__presence--none': attribute.present_on === 0 }"
                >
                  {{ presenceLabel(attribute) }}
                </span>
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
                v-if="lens.colourBy === attribute.name"
                class="key"
              >
                <label
                  v-for="step in keyFor(attribute)"
                  :key="step.label"
                  class="key__step"
                >
                  <input
                    class="key__swatch"
                    type="color"
                    :value="step.colour"
                    :title="`Pick the colour for ${step.label}`"
                    @input="pick(step, ($event.target as HTMLInputElement).value)"
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
          </ul>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.reading { border: 1px solid #e5e7eb; border-radius: 6px; background: #fff; font-size: 0.85rem; }
.reading--active { border-color: #2563eb; }
.reading__toggle {
  display: flex; align-items: baseline; gap: 0.5rem; width: 100%; padding: 0.4rem 0.6rem;
  background: none; border: none; cursor: pointer; text-align: left; font: inherit;
}
.reading__title { font-weight: 600; }
.reading__summary { color: #2563eb; }
.reading__hint, .reading__busy, .type__drawn, .type__summary, .attr__type, .attr__presence {
  color: #6b7280; font-size: 0.8rem;
}
.reading__busy { margin-left: auto; }
.reading__body { padding: 0 0.6rem 0.6rem; }
.reading__note { color: #6b7280; margin: 0.2rem 0; }
.chev { display: inline-block; transition: transform 0.12s; }
.chev--open { transform: rotate(90deg); }
.type { border-top: 1px solid #f3f4f6; }
.type__head {
  display: flex; align-items: baseline; gap: 0.5rem; width: 100%; padding: 0.35rem 0;
  background: none; border: none; cursor: pointer; text-align: left; font: inherit;
}
.type__name { font-family: ui-monospace, monospace; }
.type__summary { margin-left: auto; }
.attrs { list-style: none; margin: 0 0 0.3rem 1.2rem; padding: 0; }
.attr { padding: 0.15rem 0; }
.attr__row { display: flex; align-items: baseline; gap: 0.5rem; }
.attr__name { font-family: ui-monospace, monospace; }
.attr__presence--none { color: #d97706; }
/* The controls are one group pushed to the right, rather than each control finding its own way
   there: "no colour" is a `span` where a colour choice is a `label`, so a `:first-of-type` rule
   aligned the choices and left the absences stranded mid-row. */
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
.key__revert {
  font: inherit; font-size: 0.75rem; color: #6b7280; background: none; border: none;
  padding: 0; text-decoration: underline; cursor: pointer;
}
.key__revert:hover { color: #374151; }
.key__note { color: #9ca3af; font-size: 0.75rem; }
</style>
