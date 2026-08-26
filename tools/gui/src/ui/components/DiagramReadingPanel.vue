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
 * **A colouring shows its key.** Checking `colour` unfolds the mapping under the row: a ramp's two
 * endpoints, or one swatch per member of a value set. A colour a reader cannot decode is decoration,
 * and the swatches are drawn from the same generated tables the renderer resolves, so the key and the
 * picture cannot disagree.
 */
import { computed, ref } from 'vue'
import type { AttributeOffer, DiagramAttributePanel, TypeOffer } from '../../domain/schemas/diagrams'
import { isEmptyLens, type ReadingLens } from '../../domain/readingLens'
import { AD_HOC_RAMP_TOKENS } from '../../domain/types.generated'
import { tokenColor } from '../lib/viewpointStyleTokens'
import {
  canTakeColour, colourKey, foldSummary, lensSummary, presenceLabel, typeOfferLabel, withColourBy,
  withPrinted,
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
const keyFor = (attribute: AttributeOffer) => colourKey(attribute, rampEnds)
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
                    :title="
                      'A ramp needs an order and a palette needs a bounded set of values; this attribute declares neither.'
                    "
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
                <span
                  v-for="step in keyFor(attribute)"
                  :key="step.label"
                  class="key__step"
                >
                  <span
                    class="key__swatch"
                    :style="{ background: step.colour }"
                    aria-hidden="true"
                  />
                  {{ step.label }}
                </span>
                <span
                  v-if="attribute.colour === 'ramp'"
                  class="key__note"
                >values in between shade between these</span>
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
.key__swatch {
  display: inline-block; width: 0.85rem; height: 0.85rem; border-radius: 2px;
  border: 1px solid rgb(0 0 0 / 0.15);
}
.key__note { color: #9ca3af; font-size: 0.75rem; }
</style>
