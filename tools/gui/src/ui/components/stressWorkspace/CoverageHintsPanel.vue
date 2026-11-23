<script setup lang="ts">
/**
 * Coverage hints (F13), which replaced *Suggest stressors*: gaps in what the analysis has looked at,
 * from the scope and the rows. A name shows the element on the canvas; *Add a stressor about this*
 * adds a row about it; a kind adds a row of that kind. Nothing is proposed or drawn here.
 */
import type { CoverageHints, UntouchedHint } from '../../../domain/stressAnalysis/analysisProgress'

defineProps<{ hints: CoverageHints; endStateName: (rowId: string) => string }>()
const emit = defineEmits<{
  show: [id: string]
  aboutElement: [id: string]
  ofKind: [kind: string]
  openRow: [tab: 'stressors' | 'end-states', rowId: string]
  close: []
}>()

const groups = (hints: CoverageHints): readonly { title: string; items: readonly UntouchedHint[] }[] => [
  { title: 'Well-connected elements no stressor touches', items: hints.wellConnected },
  { title: 'Other elements no stressor touches', items: hints.otherUntouched },
].filter((group) => group.items.length > 0)
</script>

<template>
  <section
    class="hints"
    aria-label="Coverage hints"
    data-testid="coverage-hints"
  >
    <div class="sg-h">
      <b>Coverage hints</b>
      <button
        type="button"
        class="btn btn-sm"
        @click="emit('close')"
      >
        Close
      </button>
    </div>
    <p class="help">
      These are coverage gaps, not suggestions: what the stressors have not yet looked at. Drafting
      stressors with an agent is an MCP workflow.
    </p>
    <div
      v-for="group in groups(hints)"
      :key="group.title"
      class="hint-grp"
    >
      <p class="hg-h">
        {{ group.title }}
      </p>
      <ul>
        <li
          v-for="item in group.items"
          :key="item.id"
        >
          <button
            type="button"
            class="link-btn"
            @click="emit('show', item.id)"
          >
            {{ item.name }}
          </button>
          <span class="cnt">{{ item.relations }} relation{{ item.relations === 1 ? '' : 's' }}</span>
          <button
            type="button"
            class="btn btn-sm"
            @click="emit('aboutElement', item.id)"
          >
            Add a stressor about this
          </button>
        </li>
      </ul>
    </div>
    <div
      v-if="hints.unusedKinds.length"
      class="hint-grp"
    >
      <p class="hg-h">
        Kinds with no rows
      </p>
      <button
        v-for="kind in hints.unusedKinds"
        :key="kind"
        type="button"
        class="btn btn-sm kind"
        @click="emit('ofKind', kind)"
      >
        + {{ kind }}
      </button>
    </div>
    <div
      v-if="hints.singleStressorEndStates.length"
      class="hint-grp"
    >
      <p class="hg-h">
        End states with a single stressor
      </p>
      <button
        v-for="row in hints.singleStressorEndStates"
        :key="row"
        type="button"
        class="link-btn"
        @click="emit('openRow', 'end-states', row)"
      >
        {{ row }} {{ endStateName(row) }}
      </button>
    </div>
    <div
      v-if="hints.withoutEndState.length"
      class="hint-grp"
    >
      <p class="hg-h">
        Stressors without an end state
      </p>
      <button
        v-for="row in hints.withoutEndState"
        :key="row"
        type="button"
        class="link-btn"
        @click="emit('openRow', 'stressors', row)"
      >
        {{ row }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.hints {
  margin: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  padding: 8px 10px;
  font-size: 12.5px;
}
.sg-h { display: flex; gap: 8px; align-items: center; }
.sg-h b { flex: 1; }
.help { color: var(--text-2); font-size: 12px; margin: 2px 0 6px; }
.hint-grp { border-top: 1px solid var(--border); padding: 4px 0; display: flex; flex-wrap: wrap; gap: 4px 10px; }
.hg-h { flex-basis: 100%; font-size: 12px; margin: 2px 0; color: var(--text-2); }
.hint-grp ul { list-style: none; padding: 0; margin: 0; flex-basis: 100%; }
.hint-grp li { display: flex; gap: 8px; align-items: center; padding: 1px 0; }
.hint-grp li .link-btn { flex: 1; }
.cnt { color: var(--muted); font-size: 11.5px; }
.link-btn {
  border: none;
  background: none;
  color: var(--accent-strong);
  cursor: pointer;
  padding: 0;
  font: inherit;
  text-align: left;
}
.link-btn:hover { text-decoration: underline; }
</style>
