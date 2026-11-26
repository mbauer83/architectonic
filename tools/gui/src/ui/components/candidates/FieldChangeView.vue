<script setup lang="ts">
/**
 * One field's change, base against candidate, as `fieldChange` reads it: text word by word — unchanged words
 * plain, taken-out words struck, put-in words marked, and a long unchanged stretch folded to "… n words
 * unchanged …" that opens on a press; a short scalar replaced whole; a keyed field by key, each key's value
 * compared alone. The same rendering wherever a candidate's field changes are read.
 *
 * Not colour alone: a removal is a `<del>` and an insertion an `<ins>`, each also said in words to a screen
 * reader, which announces neither element by default.
 */
import { computed, ref, watch } from 'vue'
import { fieldChange, shownRuns } from '../../../domain/candidates/fieldChange'

const props = defineProps<{ before: unknown; after: unknown }>()

const change = computed(() => fieldChange(props.before, props.after))
const runs = computed(() => (change.value.kind === 'text' ? shownRuns(change.value.runs) : []))
/** The folded stretches the reader opened, by their place among the runs. */
const opened = ref(new Set<number>())
watch(change, () => { opened.value = new Set() })
const open = (index: number) => { opened.value = new Set([...opened.value, index]) }
/** The space between a value replaced whole and its replacement, where there are both. */
const separator = computed(() =>
  (change.value.kind === 'replaced' && change.value.before !== null && change.value.after !== null ? ' ' : ''))
const plural = (count: number): string => `${count} word${count === 1 ? '' : 's'}`
</script>

<template>
  <span
    v-if="change.kind === 'text'"
    class="fc fc--text"
    data-testid="field-change"
  ><template
    v-for="(run, index) in runs"
    :key="index"
  ><del
    v-if="run.kind === 'removed'"
    class="fc-del"
  ><span class="sr">removed: </span>{{ run.words.join('') }}</del><ins
    v-else-if="run.kind === 'added'"
    class="fc-ins"
  ><span class="sr">added: </span>{{ run.words.join('') }}</ins><button
    v-else-if="run.kind === 'folded' && !opened.has(index)"
    type="button"
    class="fc-fold"
    :aria-label="`Show ${plural(run.words.length)} unchanged`"
    @click.stop="open(index)"
  >… {{ plural(run.words.length) }} unchanged … </button><span
    v-else
    class="fc-same"
  >{{ run.words.join('') }}</span></template></span>
  <span
    v-else-if="change.kind === 'keyed'"
    class="fc fc--keyed"
    data-testid="field-change"
  ><span
    v-for="entry in change.entries"
    :key="entry.key"
    class="fc-key"
  ><span class="fc-key-name">{{ entry.key }}:</span> <FieldChangeView
    :before="entry.before"
    :after="entry.after"
  /></span></span>
  <span
    v-else
    class="fc fc--replaced"
    data-testid="field-change"
  ><del
    v-if="change.before !== null"
    class="fc-del"
  ><span class="sr">removed: </span>{{ change.before }}</del>{{ separator }}<ins
    v-if="change.after !== null"
    class="fc-ins"
  ><span class="sr">added: </span>{{ change.after }}</ins><span
    v-if="change.before === null && change.after === null"
  >—</span></span>
</template>

<style scoped>
.fc { white-space: pre-wrap; overflow-wrap: anywhere; }
.fc-del { text-decoration: line-through; color: var(--warn-text); background: var(--warn-soft); }
.fc-ins { text-decoration: none; font-weight: 600; color: var(--ok-text); background: var(--ok-soft);
  box-shadow: inset 0 -1px 0 currentcolor; }
.fc-fold {
  font: inherit; font-size: 0.92em; color: var(--muted); background: var(--soft);
  border: 1px dashed var(--border-strong); border-radius: 3px; padding: 0 4px; cursor: pointer;
}
.fc-fold:hover, .fc-fold:focus-visible { color: var(--text); border-style: solid; }
.fc--keyed { display: flex; flex-direction: column; gap: 2px; }
.fc-key-name { color: var(--muted); font-weight: 600; }
.sr {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden;
  clip-path: inset(50%); white-space: nowrap; border: 0;
}
</style>
