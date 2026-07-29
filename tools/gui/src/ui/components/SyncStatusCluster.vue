<script setup lang="ts">
/**
 * Right-aligned workflow/status cluster: repository status chip plus a Changes
 * menu housing engagement Save, enterprise Save/Submit/Discard, and the Promote
 * entry point. Nouns live in the left navigation; every verb lives here, and all
 * of them are fail-closed behind the reducer's authority handling.
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
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
        :disabled="!hasActions"
        aria-haspopup="menu"
        :aria-expanded="menuOpen"
        @click="menuOpen = !menuOpen"
      >
        Changes ▾
      </button>
      <div
        v-if="menuOpen && hasActions"
        class="cluster__menu"
        role="menu"
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
.cluster { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.cluster__status { font-size: 12px; padding: 3px 9px; border-radius: 10px; font-weight: 600; white-space: nowrap; max-width: 320px; overflow: hidden; text-overflow: ellipsis; }
.cluster__status--ok { background: #14352a; color: #6ee7b7; }
.cluster__status--info { background: #1e3a5f; color: #93c5fd; }
.cluster__status--warn { background: #422006; color: #fcd34d; }
.cluster__status--error { background: #450a0a; color: #fca5a5; }
.cluster__status--muted { background: #1f2937; color: #94a3b8; }
.cluster__behind { margin-left: 4px; color: #fbbf24; }
.cluster__menu-wrap { position: relative; }
.cluster__menu-btn { background: #2563eb; color: #fff; border: none; border-radius: 5px; font-size: 12px; font-weight: 600; padding: 4px 10px; cursor: pointer; white-space: nowrap; }
.cluster__menu-btn:hover:not(:disabled) { background: #1d4ed8; }
.cluster__menu-btn:disabled { background: #334155; color: #64748b; cursor: not-allowed; }
.cluster__menu { position: absolute; right: 0; top: calc(100% + 6px); min-width: 220px; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,.18); padding: 4px 0; z-index: 60; }
.cluster__menu-item { display: block; width: 100%; padding: 8px 14px; border: none; background: none; cursor: pointer; text-align: left; font-size: 13px; color: #1f2937; white-space: nowrap; }
.cluster__menu-item:hover { background: #f1f5f9; color: #1d4ed8; }
</style>
