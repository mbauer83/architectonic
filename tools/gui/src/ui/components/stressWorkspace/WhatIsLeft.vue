<script setup lang="ts">
/**
 * "What is left" (06·8): the progress read as sentences, each a link that opens the tab and the row
 * it is about. Completeness is asked for only at commit; until then this only informs.
 */
import { computed, ref } from 'vue'
import type { AnalysisProgress } from '../../../domain/schemas/candidates'
import type { LeftItem, WorkspaceTab } from '../../../domain/stressAnalysis/analysisProgress'
import { whatIsLeft } from '../../../domain/stressAnalysis/analysisProgress'

const props = defineProps<{ progress: AnalysisProgress | null }>()
const emit = defineEmits<{ open: [tab: WorkspaceTab, row: string] }>()

const open = ref(false)
const items = computed(() => props.progress ? whatIsLeft(props.progress.progress) : [])
const go = (item: LeftItem) => {
  open.value = false
  emit('open', item.tab, item.row)
}
</script>

<template>
  <div
    class="left"
    data-testid="what-is-left"
  >
    <button
      type="button"
      class="left-sum"
      :aria-expanded="open"
      @click="open = !open"
    >
      What is left: {{ items.length }} ▾
    </button>
    <div
      v-if="open"
      class="progress-pop"
    >
      <p v-if="!items.length">
        Nothing is left: every stressor is walked and grouped, and every end state answered.
      </p>
      <ul v-else>
        <li
          v-for="item in items"
          :key="item.key"
        >
          <button
            type="button"
            class="link-btn"
            @click="go(item)"
          >
            {{ item.text }}
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.left { position: relative; }
.left-sum {
  border: none;
  background: none;
  color: var(--accent-strong);
  cursor: pointer;
  font: inherit;
  font-size: 14px;
}
.progress-pop {
  position: absolute; right: 0; top: calc(100% + 6px); z-index: 20; width: 380px; padding: 10px 12px;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: var(--shadow);
  font-size: 12.5px;
}
.progress-pop ul { margin: 0; padding: 0 0 0 16px; }
.progress-pop li { margin: 0 0 4px; }
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
