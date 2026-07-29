<script setup lang="ts">
import { computed } from 'vue'
import type { WizardSuggestion } from '../composables/useWizardSession'
import type { AuthoringGuidance } from '../../domain'
import { connectionCreationGuidance, connectionTypeLabel } from '../lib/connectionTypeGuidance'

/**
 * Ranked connection suggestions with accept/later/dismiss. Each row can disclose the relationship
 * type's own creation guidance, collapsed by default: the wizard is where the relationship is still
 * being chosen, so the framing belongs here rather than in the ordinary connection forms.
 */
const props = defineProps<{
  suggestions: WizardSuggestion[]
  busy?: boolean
  hideLater?: boolean
  /** Omitted where no guidance has been fetched — rows then render without the disclosure. */
  guidance?: AuthoringGuidance | null
}>()
const emit = defineEmits<{
  accept: [suggestion: WizardSuggestion]
  dismiss: [id: string]
  later: [id: string]
}>()

/** Each row with its relationship guidance resolved once, rather than per template reference. */
const rows = computed(() => props.suggestions.map((suggestion) => ({
  suggestion,
  typeLabel: connectionTypeLabel(suggestion.connectionType),
  guidance: connectionCreationGuidance(props.guidance ?? null, suggestion.connectionType),
})))
</script>

<template>
  <ul
    v-if="suggestions.length"
    class="suggestion-list"
  >
    <li
      v-for="row in rows"
      :key="row.suggestion.id"
      class="suggestion-row"
    >
      <span class="suggestion-main">
        <span class="suggestion-summary">{{ row.suggestion.summary }}</span>
        <details
          v-if="row.guidance"
          class="conn-guidance"
        >
          <summary>When to use {{ row.typeLabel }}</summary>
          <p
            v-if="row.guidance.createWhen"
            class="conn-guidance__text"
          >
            {{ row.guidance.createWhen }}
          </p>
          <p
            v-if="row.guidance.neverCreateWhen"
            class="conn-guidance__text conn-guidance__text--never"
          >
            {{ row.guidance.neverCreateWhen }}
          </p>
        </details>
      </span>
      <span class="suggestion-actions">
        <button
          type="button"
          class="btn-accept"
          :disabled="busy"
          @click="emit('accept', row.suggestion)"
        >
          Accept
        </button>
        <button
          v-if="!hideLater"
          type="button"
          class="btn-later"
          :disabled="busy"
          @click="emit('later', row.suggestion.id)"
        >
          Later
        </button>
        <button
          type="button"
          class="btn-dismiss"
          :disabled="busy"
          @click="emit('dismiss', row.suggestion.id)"
        >
          Dismiss
        </button>
      </span>
    </li>
  </ul>
  <p
    v-else
    class="suggestion-empty"
  >
    No connection suggestions yet.
  </p>
</template>

<style scoped>
.suggestion-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.suggestion-row {
  /* flex-start, not center: an expanded guidance disclosure grows the row, and the actions should
     stay beside the summary they act on rather than drifting down with it. */
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  padding: 8px 12px; border: 1px solid #e5e7eb; border-radius: 6px; background: #fafafa;
}
.suggestion-main { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.suggestion-summary { font-size: 13px; color: #374151; }
.conn-guidance { font-size: 12px; color: #6b7280; }
.conn-guidance summary { cursor: pointer; }
.conn-guidance__text { margin: 4px 0 0; }
.conn-guidance__text--never { color: #b45309; }
.suggestion-actions { display: flex; gap: 6px; flex-shrink: 0; }
.suggestion-actions button {
  font-size: 12px; padding: 4px 10px; border-radius: 5px; cursor: pointer; border: 1px solid transparent;
}
.suggestion-actions button:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-accept { background: #16a34a; color: white; }
.btn-later { background: white; border-color: #d1d5db; color: #4b5563; }
.btn-dismiss { background: white; border-color: #fecaca; color: #dc2626; }
.suggestion-empty { color: #9ca3af; font-size: 13px; }
</style>
