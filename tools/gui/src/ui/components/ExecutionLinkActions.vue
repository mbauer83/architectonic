<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import type { LocationQueryRaw } from 'vue-router'
import { VERIFIED_KEYS, verifiedReferenceQuery, type VerifiedPins } from '../lib/viewpointUrlState'

/** Two link affordances with honestly different contracts: a LIVE link re-executes
 * against current model/definition state and silently changes as they change; a VERIFIED
 * reference additionally pins definition version/digest and model generation so opening
 * it later can say the state moved. Neither archives results. */
const props = defineProps<{
  pins: VerifiedPins | null
}>()

const route = useRoute()
const copied = ref<'live' | 'verified' | null>(null)

const urlFor = (query: LocationQueryRaw): string => {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (typeof value === 'string') search.set(key, value)
  }
  return `${window.location.origin}${window.location.pathname}#${route.path}?${search.toString()}`
}

const liveQuery = (): LocationQueryRaw => {
  const query: LocationQueryRaw = { ...route.query }
  for (const key of VERIFIED_KEYS) delete query[key]
  return query
}

const copy = (kind: 'live' | 'verified') => {
  const query = kind === 'live' || props.pins === null
    ? liveQuery()
    : verifiedReferenceQuery(liveQuery(), props.pins)
  void navigator.clipboard.writeText(urlFor(query)).then(() => {
    copied.value = kind
    setTimeout(() => { copied.value = null }, 1500)
  })
}
</script>

<template>
  <div class="link-actions">
    <button
      type="button"
      class="link-btn"
      title="Copy a LIVE link: it re-executes against current model and definition state and changes as they change"
      @click="copy('live')"
    >
      {{ copied === 'live' ? '✓ copied' : '🔗 Copy link (live)' }}
    </button>
    <button
      v-if="pins !== null"
      type="button"
      class="link-btn"
      title="Copy a VERIFIED reference: pins the definition version/digest and model generation, so opening it later reports when state has moved"
      @click="copy('verified')"
    >
      {{ copied === 'verified' ? '✓ copied' : '🔒 Copy verified reference' }}
    </button>
  </div>
</template>

<style scoped>
.link-actions { display: inline-flex; gap: 6px; }
.link-btn {
  font-size: 11.5px; padding: 3px 10px; border: 1px solid #d1d5db; border-radius: 5px;
  background: white; cursor: pointer; color: #374151; white-space: nowrap;
}
.link-btn:hover { background: #f9fafb; }
</style>
