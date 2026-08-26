<script setup lang="ts">
/**
 * The display options for one diagram: colour the elements by an attribute, print values with them.
 *
 * Called what it is. It was headed "Reading" — the word this codebase uses internally for an ad-hoc,
 * unpersisted view of a diagram — which says nothing to somebody looking at a panel of checkboxes and
 * wondering what it adjusts.
 *
 * **Unobtrusive by construction.** It is folded away by default and, folded, still says what is
 * active — a reader who set a heat map, scrolled, and came back must not have to reopen the panel to
 * find out why the picture is orange. Inside, one row per entity type and specialization the diagram
 * actually draws, each folding to its attributes; nothing is offered that no drawn element could
 * answer for.
 *
 * **What reads across the diagram comes first.** Colouring is by attribute name and applies to every
 * drawn entity that has one, so an attribute several types declare identically is a global reading —
 * and burying it inside each type's fold would say the opposite. Those rows sit above the types,
 * unfolded, and their members still appear in their own type folds where the per-type presence count
 * lives. A name several types declare *differently* is called out instead of quietly left out: it can
 * still be coloured by, globally, and it would put two meanings on one scale.
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
  isEmptyLens, withLegendMark, withMemberColour, withRampEnd,
  LEGEND_MARKS, LEGEND_MARK_MEANING, type ReadingLens,
} from '../../domain/readingLens'
import { AD_HOC_RAMP_TOKENS } from '../../domain/types.generated'
import { tokenColor } from '../lib/viewpointStyleTokens'
import DiagramReadingAttributeRow from './DiagramReadingAttributeRow.vue'
import { colourKey, foldSummary, lensSummary, typeOfferLabel, type ColourStep } from './DiagramReadingPanel.helpers'

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


// A colour input always reports `#rrggbb`, which is what the wire and the renderer both want, so the
// value goes through untouched — the server validates it again regardless, because a query string is
// not a trusted source however this page behaves.
const pick = (step: ColourStep, colour: string) => emit(
  'update:lens',
  step.kind === 'member'
    ? withMemberColour(props.lens, step.member, colour)
    : withRampEnd(props.lens, step.end, colour, rampEnds),
)
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
      <span class="reading__title">Display options</span>
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
        <!-- Either half is reason to show this. The disputed line used to sit inside the shared
             check, so a diagram whose only cross-type attributes *disagreed* showed nothing at all —
             which is precisely the silence naming them is meant to break. -->
        <!-- The legend explains the notation the picture already carries, so it is not about any one
             type and sits above the rows rather than inside them. It is drawn *into* the image, which
             is what makes it export with an SVG or a PNG. -->
        <div class="marks">
          <p class="marks__head">
            Explain the notation, in the image
          </p>
          <span class="marks__options">
            <label
              v-for="mark in LEGEND_MARKS"
              :key="mark"
              class="attr__control"
              :title="LEGEND_MARK_MEANING[mark]"
            >
              <input
                type="checkbox"
                :checked="lens.legends.includes(mark)"
                @change="emit('update:lens', withLegendMark(lens, mark))"
              >
              {{ mark }}
            </label>
          </span>
        </div>

        <div
          v-if="panel.shared.length || panel.disputed.length"
          class="across"
        >
          <p
            v-if="panel.shared.length"
            class="across__head"
          >
            Across every type that declares it
          </p>
          <ul
            v-if="panel.shared.length"
            class="attrs attrs--across"
          >
            <DiagramReadingAttributeRow
              v-for="offer in panel.shared"
              :key="offer.attribute.name"
              :attribute="offer.attribute"
              :lens="lens"
              :on-rows="offer.on_rows"
              @update:lens="emit('update:lens', $event)"
            />
          </ul>
          <p
            v-if="panel.disputed.length"
            class="across__disputed"
          >
            Declared differently by different types, so one colouring would mix two meanings:
            {{ panel.disputed.join(', ') }}
          </p>
        </div>

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
            <DiagramReadingAttributeRow
              v-for="attribute in offer.attributes"
              :key="attribute.name"
              :attribute="attribute"
              :lens="lens"
              :colour-key="keyFor(attribute)"
              @update:lens="emit('update:lens', $event)"
              @pick="pick"
            />
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
.reading__hint, .reading__busy, .type__drawn, .type__summary { color: #6b7280; font-size: 0.8rem; }
.reading__busy { margin-left: auto; }
.reading__body { padding: 0 0.6rem 0.6rem; }
.reading__note { color: #6b7280; margin: 0.2rem 0; }
.chev { display: inline-block; transition: transform 0.12s; }
.chev--open { transform: rotate(90deg); }
.marks { display: flex; align-items: baseline; gap: 0.75rem; padding: 0.35rem 0 0.4rem; }
.marks__head { margin: 0; font-size: 0.8rem; color: #6b7280; }
.marks__options { display: inline-flex; align-items: baseline; gap: 0.75rem; margin-left: auto; }
.marks .attr__control { display: inline-flex; align-items: baseline; gap: 0.2rem; cursor: pointer; }
.across { border-top: 1px solid #f3f4f6; padding-bottom: 0.2rem; }
.across__head { margin: 0.35rem 0 0.1rem; font-size: 0.8rem; color: #6b7280; }
.across__disputed { margin: 0.2rem 0 0 1.2rem; font-size: 0.75rem; color: #d97706; }
.attrs--across { margin-left: 1.2rem; }
.type { border-top: 1px solid #f3f4f6; }
.type__head {
  display: flex; align-items: baseline; gap: 0.5rem; width: 100%; padding: 0.35rem 0;
  background: none; border: none; cursor: pointer; text-align: left; font: inherit;
}
.type__name { font-family: ui-monospace, monospace; }
.type__summary { margin-left: auto; }
.attrs { list-style: none; margin: 0 0 0.3rem 1.2rem; padding: 0; }
</style>
