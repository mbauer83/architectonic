<script setup lang="ts">
/**
 * Right-aligned workflow/status cluster: repository status chip plus a Changes
 * menu housing engagement Save, enterprise Save/Submit/Discard, and the Promote
 * entry point. The verbs are fail-closed behind the reducer's authority handling.
 *
 * The menu also opens the Proposed changes page. That destination is not on the
 * artifact axis the left navigation is for — Browse, Documents, Diagrams and the
 * rest are classes of artifact, while this is the state of the enterprise-change
 * workflow, which is what this cluster owns. It is a destination and not an
 * action, so it does not pass through the reducer and is not authority-gated:
 * reading which changes exist and where they stand is not a write. That is also
 * why the button no longer disables itself when the reducer offers nothing —
 * there is always something to open, and a submission waiting on review is
 * exactly the situation in which there is nothing left to do.
 */
import { computed, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import type { EnterpriseSyncStatus, SyncAuthority } from '../../domain'
import { reduceCluster, type ClusterAction } from './SyncStatusCluster.helpers'

type SaveMode = 'engagement-save' | 'enterprise-save' | 'enterprise-submit' | 'enterprise-withdraw'

const props = defineProps<{
  authorityKnown: boolean
  authority: SyncAuthority | null
  enterprise: EnterpriseSyncStatus | null
  engagementDirty: boolean
}>()
const emit = defineEmits<{ openSaveDialog: [mode: SaveMode] }>()

const router = useRouter()
const menuOpen = ref(false)
const menuButton = ref<HTMLButtonElement | null>(null)

const model = computed(() =>
  reduceCluster({
    authorityKnown: props.authorityKnown,
    authority: props.authority,
    enterprise: props.enterprise,
    engagementDirty: props.engagementDirty,
  }),
)

const ACTION_LABELS: Record<ClusterAction, string> = {
  engagement_save: 'Save engagement changes',
  enterprise_save: 'Save enterprise changes',
  enterprise_submit: 'Submit for review',
  enterprise_discard_local: 'Discard working branch',
  enterprise_discard_pending: 'Discard submission',
  promote: 'Promote to enterprise…',
}

const menuActions = computed<ClusterAction[]>(() => [
  ...(model.value.engagementSaveAvailable ? (['engagement_save'] as const) : []),
  ...model.value.actions,
])

const hasActions = computed(() => menuActions.value.length > 0)

const runAction = (action: ClusterAction) => {
  menuOpen.value = false
  switch (action) {
    case 'engagement_save':
      emit('openSaveDialog', 'engagement-save')
      break
    case 'enterprise_save':
      emit('openSaveDialog', 'enterprise-save')
      break
    case 'enterprise_submit':
      emit('openSaveDialog', 'enterprise-submit')
      break
    case 'enterprise_discard_local':
    case 'enterprise_discard_pending':
      emit('openSaveDialog', 'enterprise-withdraw')
      break
    case 'promote':
      void router.push('/promote')
      break
  }
}

const closeMenu = () => {
  menuOpen.value = false
  menuButton.value?.focus()
}
</script>

<template>
  <div
    class="cluster"
    role="group"
    aria-label="Repository workflow and status"
  >
    <span
      class="cluster__status"
      :class="`cluster__status--${model.tone}`"
      :title="model.behindWarning ?? undefined"
    >
      {{ model.presentation }}
      <span
        v-if="model.behindWarning"
        class="cluster__behind"
        role="img"
        :aria-label="model.behindWarning"
      >⇣</span>
    </span>
    <div
      class="cluster__menu-wrap"
      @keydown.escape="closeMenu"
      @focusout="(e) => { if (!(e.currentTarget as Node).contains(e.relatedTarget as Node)) menuOpen = false }"
    >
      <button
        ref="menuButton"
        class="cluster__menu-btn"
        aria-haspopup="menu"
        :aria-expanded="menuOpen"
        @click="menuOpen = !menuOpen"
      >
        Changes ▾
      </button>
      <div
        v-if="menuOpen"
        class="cluster__menu"
        role="menu"
      >
        <RouterLink
          class="cluster__menu-item"
          role="menuitem"
          to="/changes"
          title="Edits to artifacts this repository does not own, held until they are accepted upstream"
          @click="menuOpen = false"
        >
          Proposed changes
        </RouterLink>
        <hr
          v-if="hasActions"
          class="cluster__menu-rule"
        >
        <button
          v-for="action in menuActions"
          :key="action"
          class="cluster__menu-item"
          role="menuitem"
          @click="runAction(action)"
        >
          {{ ACTION_LABELS[action] }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* The chip is what yields when the bar is short: it already ellipsises, and a status sentence
   losing its tail still reads. The menu button never shrinks — it is the only way to reach the
   write actions. */
.cluster { display: flex; align-items: center; gap: 8px; min-width: 0; }
.cluster__status { flex-shrink: 1; min-width: 0; font-size: 12px; padding: 3px 9px; border-radius: 10px; font-weight: 600; white-space: nowrap; max-width: 320px; overflow: hidden; text-overflow: ellipsis; }
.cluster__status--ok { background: #14352a; color: #6ee7b7; }
.cluster__status--info { background: #1e3a5f; color: #93c5fd; }
.cluster__status--warn { background: #422006; color: #fcd34d; }
.cluster__status--error { background: #450a0a; color: #fca5a5; }
.cluster__status--muted { background: #1f2937; color: #94a3b8; }
.cluster__behind { margin-left: 4px; color: #fbbf24; }
.cluster__menu-wrap { position: relative; flex-shrink: 0; }
.cluster__menu-btn { background: #2563eb; color: #fff; border: none; border-radius: 5px; font-size: 12px; font-weight: 600; padding: 4px 10px; cursor: pointer; white-space: nowrap; }
.cluster__menu-btn:hover:not(:disabled) { background: #1d4ed8; }
.cluster__menu-rule { border: none; border-top: 1px solid #e2e8f0; margin: 4px 0; }
.cluster__menu { position: absolute; right: 0; top: calc(100% + 6px); min-width: 220px; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,.18); padding: 4px 0; z-index: 60; }
.cluster__menu-item { display: block; width: 100%; box-sizing: border-box; text-decoration: none; padding: 8px 14px; border: none; background: none; cursor: pointer; text-align: left; font-size: 13px; color: #1f2937; white-space: nowrap; }
.cluster__menu-item:hover { background: #f1f5f9; color: #1d4ed8; }
</style>
