<script setup lang="ts">
/**
 * The advice about one element, as loud as its status says and no louder.
 *
 * `marker` (a draft): a small count that opens to the findings — no banner, no toast. `listed` (an
 * active element): each finding with its reason. Either way an advice can be accepted with a short
 * reason, and an accepted one is shown as "Accepted: …" in its place; withdrawing the acceptance lets
 * it speak again. The panel writes nothing itself: it emits the acknowledgement set to store, and the
 * page saves it through the ordinary entity edit.
 */

import { computed, ref } from 'vue'
import type { EntityAdvice } from '../../domain/schemas/entities'
import { type AcceptedAdviceEntry, acknowledging, adviceCountLabel, hasAReason, withdrawing } from './entityAdvice'

const props = defineProps<{ advice: EntityAdvice; busy?: boolean }>()
const emit = defineEmits<{ acknowledge: [entries: AcceptedAdviceEntry[]] }>()

const drafting = ref<string | null>(null)
const reason = ref('')
const label = computed(() => adviceCountLabel(props.advice.open.length))

const startAccepting = (code: string) => {
  drafting.value = code
  reason.value = ''
}
const accept = (code: string) => {
  if (!hasAReason(reason.value)) return
  emit('acknowledge', acknowledging(props.advice.accepted, code, reason.value))
  drafting.value = null
}
const withdraw = (code: string) => emit('acknowledge', withdrawing(props.advice.accepted, code))
</script>

<template>
  <div
    v-if="advice.open.length || advice.accepted.length"
    class="advice"
    data-testid="entity-advice"
  >
    <component
      :is="advice.presentation === 'marker' ? 'details' : 'div'"
      v-if="advice.open.length"
      :class="advice.presentation === 'marker' ? 'advice-marker' : 'card advice-card'"
      :data-testid="advice.presentation === 'marker' ? 'advice-marker' : 'advice-list'"
    >
      <summary
        v-if="advice.presentation === 'marker'"
        class="marker-summary"
      >
        <span class="marker-dot" />{{ label }}
      </summary>
      <h2
        v-else
        class="section-title"
      >
        Advice
      </h2>
      <ul class="advice-items">
        <li
          v-for="issue in advice.open"
          :key="issue.code"
          class="advice-item"
        >
          <code class="advice-code">{{ issue.code }}</code>
          <span class="advice-message">{{ issue.message }}</span>
          <form
            v-if="drafting === issue.code"
            class="accept-form"
            @submit.prevent="accept(issue.code)"
          >
            <input
              v-model="reason"
              class="accept-reason"
              placeholder="Why the element is right as it stands"
              aria-label="Reason for accepting this advice"
            >
            <button
              type="submit"
              class="btn-link"
              :disabled="busy || !hasAReason(reason)"
            >
              Accept
            </button>
            <button
              type="button"
              class="btn-link"
              @click="drafting = null"
            >
              Cancel
            </button>
          </form>
          <button
            v-else
            type="button"
            class="btn-link"
            :disabled="busy"
            @click="startAccepting(issue.code)"
          >
            Accept…
          </button>
        </li>
      </ul>
    </component>
    <ul
      v-if="advice.accepted.length"
      class="accepted-items"
      data-testid="advice-accepted"
    >
      <li
        v-for="entry in advice.accepted"
        :key="entry.code"
        class="accepted-item"
        :title="entry.title"
      >
        Accepted: {{ entry.reason }} <code class="advice-code">{{ entry.code }}</code>
        <button
          type="button"
          class="btn-link"
          :disabled="busy"
          @click="withdraw(entry.code)"
        >
          Withdraw
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.advice { margin-bottom: 16px; font-size: 12px; color: var(--muted); }
.card { background: var(--surface); border-radius: 8px; border: 1px solid var(--border); }
.advice-card { padding: 14px 16px; margin-bottom: 8px; color: var(--text); }
.section-title { font-size: 14px; font-weight: 700; margin: 0 0 10px; color: var(--text); }
.advice-marker { display: inline-block; margin-bottom: 8px; }
.marker-summary { cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
.marker-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); display: inline-block; }
.advice-items, .accepted-items { list-style: none; display: flex; flex-direction: column; gap: 6px; padding: 0; }
.advice-marker .advice-items { margin-top: 6px; }
.advice-item, .accepted-item { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; font-size: 12px; }
.advice-code { font-size: 11px; color: var(--muted); }
.advice-message { color: var(--text); }
.accept-form { display: inline-flex; gap: 6px; align-items: baseline; }
.accept-reason { font-size: 12px; min-width: 260px; }
.btn-link { background: none; border: none; color: var(--accent-strong); cursor: pointer; font-size: 12px; padding: 0; }
.btn-link:disabled { color: var(--muted); cursor: default; }
</style>
