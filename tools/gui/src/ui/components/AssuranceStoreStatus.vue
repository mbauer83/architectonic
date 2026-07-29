<script setup lang="ts">
/**
 * The assurance store's lock state, shown only when it stands in the reader's way.
 *
 * This used to be a page of its own — a hub whose main content was a banner saying the store was
 * fine, plus a link to the actual node list. The banner belongs with the content it gates, so it
 * lives here and the browse surface renders it above the list. An unlocked store shows nothing at
 * all: a permanent green strip is noise, and noise is what makes a reader miss the red one.
 *
 * Which message applies is decided in the helpers, where it is tested. Always callable — the
 * status endpoint needs no unlocked store, which is what lets this render the locked case.
 */
import { onMounted, ref, computed } from 'vue'
import {
  GETTING_STARTED,
  bannerFor,
  type AssuranceStatus,
} from './AssuranceStoreStatus.helpers'

const status = ref<AssuranceStatus | null>(null)
const error = ref<string | null>(null)

const banner = computed(() => bannerFor(status.value))

onMounted(async () => {
  try {
    const resp = await fetch('/api/assurance/status')
    if (!resp.ok) {
      error.value = `Could not read the assurance store status (HTTP ${resp.status}).`
      return
    }
    status.value = await resp.json() as AssuranceStatus
  } catch (cause) {
    error.value = String(cause)
  }
})
</script>

<template>
  <div
    v-if="error"
    class="store-status store-status--error"
  >
    {{ error }}
  </div>
  <div
    v-else-if="banner"
    class="store-status"
    :class="`store-status--${banner.state}`"
  >
    <div class="store-status__icon">
      🔒
    </div>
    <div class="store-status__body">
      <p class="store-status__title">
        {{ banner.title }}
      </p>
      <p class="store-status__hint">
        {{ banner.hint }}
        <code>{{ banner.command }}</code>
      </p>
      <ol
        v-if="banner.showGettingStarted"
        class="store-status__steps"
      >
        <li
          v-for="step in GETTING_STARTED"
          :key="step.command"
        >
          <code>{{ step.command }}</code> — {{ step.then }}
        </li>
      </ol>
    </div>
  </div>
</template>

<style scoped>
.store-status {
  display: flex; align-items: flex-start; gap: 14px;
  padding: 14px 18px; border-radius: 8px; margin-bottom: 16px;
  border: 1px solid #e2e8f0; font-size: 13px;
}
.store-status--not_initialised { background: #fef3c7; border-color: #fcd34d; }
.store-status--locked { background: #fee2e2; border-color: #fca5a5; }
.store-status--error { background: #f3f4f6; border-color: #d1d5db; color: #374151; }
.store-status__icon { font-size: 20px; flex-shrink: 0; }
.store-status__title { font-weight: 600; margin: 0 0 4px; }
.store-status__hint { margin: 0; color: #374151; line-height: 1.5; }
.store-status__steps { margin: 10px 0 0; padding-left: 20px; line-height: 1.8; color: #374151; }
.store-status code { background: rgba(0, 0, 0, .07); padding: 1px 5px; border-radius: 3px; }
</style>
